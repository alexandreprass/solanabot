import json
import os
from datetime import datetime, timedelta
from solana.rpc.api import Client
from solders.pubkey import Pubkey # Certifique-se que 'solders' está no requirements.txt
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from http import HTTPStatus
import asyncio
import logging # Adicionado para melhor depuração

# Configurar logging básico para Vercel
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurações (carregadas no início do módulo)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") # Obter da variável de ambiente no Vercel
QUICKNODE_URL = os.environ.get("QUICKNODE_URL")   # Obter da variável de ambiente no Vercel
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

# Armazenamento em memória (será resetado entre invocações em ambientes serverless,
# a menos que a instância da função seja reutilizada - "warm start")
competitions = {}  # {chat_id: {"token_address": str, "start_time": datetime, "period_days": int}}
wallets = {}  # {chat_id: {user_id: wallet_address}}

# Conexão com QuickNode
# É importante tratar a ausência de QUICKNODE_URL
if QUICKNODE_URL:
    try:
        solana_client = Client(QUICKNODE_URL)
        logger.info("Conexão com QuickNode estabelecida com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao inicializar cliente Solana: {e}")
        solana_client = None # Define como None para poder verificar depois
else:
    logger.error("QUICKNODE_URL não está configurada como variável de ambiente.")
    solana_client = None

# Registrar carteira
async def register_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Comando /registerwallet recebido de {update.message.from_user.id}")
    chat_id = str(update.message.chat_id)
    user_id = update.message.from_user.id
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Use: /registerwallet <endereço_da_carteira>")
        return
    wallet_address = args[0]
    try:
        Pubkey.from_string(wallet_address)  # Valida endereço Solana
        if chat_id not in wallets:
            wallets[chat_id] = {}
        wallets[chat_id][user_id] = wallet_address
        await update.message.reply_text(f"Carteira {wallet_address} registrada com sucesso!")
        logger.info(f"Carteira {wallet_address} registrada para o usuário {user_id} no chat {chat_id}")
    except Exception as e:
        logger.error(f"Erro ao registrar carteira {wallet_address}: {e}")
        await update.message.reply_text(f"Erro: Endereço inválido. Detalhe: {str(e)}")

# Iniciar competição
async def start_comp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Comando /startcomp recebido de {update.message.from_user.id}")
    chat_id = str(update.message.chat_id)
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Use: /startcomp <endereço_do_token> <período_em_dias>")
        return
    token_address, period_str = args
    try:
        period_days = int(period_str.replace("d", ""))
        Pubkey.from_string(token_address)  # Valida endereço do token
        competitions[chat_id] = {
            "token_address": token_address,
            "start_time": datetime.now(),
            "period_days": period_days
        }
        await update.message.reply_text(f"Competição iniciada para o token {token_address} por {period_days} dias!")
        logger.info(f"Competição iniciada no chat {chat_id} para o token {token_address} por {period_days} dias.")
    except ValueError:
        logger.error(f"Período inválido fornecido: {period_str}")
        await update.message.reply_text("Erro: O período deve ser um número (ex: '7d' para 7 dias).")
    except Exception as e:
        logger.error(f"Erro ao iniciar competição para token {token_address}: {e}")
        await update.message.reply_text(f"Erro ao iniciar competição: {str(e)}")

# Consultar transações e gerar ranking
async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Comando /ranking recebido de {update.message.from_user.id}")
    chat_id = str(update.message.chat_id)

    if not solana_client:
        logger.error("Cliente Solana não inicializado. Verifique a URL do QuickNode.")
        await update.message.reply_text("Erro interno: Não foi possível conectar ao serviço Solana.")
        return

    if chat_id not in competitions:
        await update.message.reply_text("Nenhuma competição ativa neste grupo.")
        return
        
    comp = competitions[chat_id]
    token_address = comp["token_address"]
    start_time = comp["start_time"]
    period_days = comp["period_days"]
    end_time = start_time + timedelta(days=period_days)

    if datetime.now() > end_time:
        await update.message.reply_text("A competição terminou!")
        # Aqui você poderia limpar a competição: del competitions[chat_id]
        return

    await update.message.reply_text("Calculando ranking, por favor aguarde...")

    try:
        token_pubkey = Pubkey.from_string(token_address)
        # Nota: get_signatures_for_address pode ser lento ou retornar muitas transações.
        # Considere estratégias de paginação ou limites mais agressivos se necessário.
        signatures_response = solana_client.get_signatures_for_address(
            token_pubkey,
            limit=100 # Limite razoável para começar
        )
        signatures = signatures_response.value if signatures_response else []
        logger.info(f"Obtidas {len(signatures)} assinaturas para o token {token_address}")

        volumes = {} # {wallet_address: volume}
        processed_signatures = 0
        for sig_info in signatures:
            if sig_info.block_time is None:
                continue
            
            tx_time = datetime.fromtimestamp(sig_info.block_time)
            # Filtrar transações fora do período da competição
            if not (start_time <= tx_time <= end_time):
                continue
            
            processed_signatures += 1
            # Para evitar sobrecarregar a API com get_transaction, pode ser necessário otimizar.
            # Em um cenário real, processar muitas transações assim pode ser custoso/lento.
            transaction_detail = solana_client.get_transaction(sig_info.signature, max_supported_transaction_version=0)
            tx = transaction_detail.value if transaction_detail else None

            if not tx or not tx.transaction or not tx.transaction.message:
                logger.warning(f"Não foi possível obter detalhes da transação para a assinatura: {sig_info.signature}")
                continue

            for instruction in tx.transaction.message.instructions:
                if instruction.program_id == TOKEN_PROGRAM_ID:
                    # Decodificar instrução de transferência (opcode 3 para Token Program)
                    # Dados da instrução: [opcode (1 byte), amount (8 bytes)]
                    if len(instruction.data) >= 9 and instruction.data[0] == 3: # Transfer instruction
                        # Verifique se as contas esperadas estão presentes
                        # instruction.accounts[0] = source
                        # instruction.accounts[1] = mint (não, é destination para transfer)
                        # instruction.accounts[2] = authority
                        # No schema de Token Program, para Transfer:
                        # 0. Source Account
                        # 1. Destination Account
                        # 2. Owner of Source Account
                        
                        # O schema das contas para uma instrução de transferência é [source, destination, authority]
                        # Estamos interessados na conta de destino (accounts[1])
                        # No entanto, a lógica original parece mapear instruction.accounts[1] como destination.
                        # Confirmando: get_signatures_for_address retorna para o token_address.
                        # Precisamos identificar transferências *para* carteiras registradas.
                        
                        # Para token transfers, accounts[0] é a conta de origem, accounts[1] é a conta de destino
                        # do token, e accounts[2] é a autoridade da conta de origem.
                        
                        # A lógica anterior usava instruction.accounts[1] como 'destination'.
                        # Se instruction.accounts são os índices das contas na tx.transaction.message.account_keys:
                        msg_accounts = tx.transaction.message.account_keys
                        
                        if len(instruction.accounts) > 1: # Deve ter pelo menos source e destination
                            try:
                                # destination_account_index = instruction.accounts[1] # Índice na lista de contas da transação
                                # destination_pubkey_obj = msg_accounts[destination_account_index]
                                # destination_wallet_address = str(destination_pubkey_obj)

                                # A lógica de `instruction.accounts` é que eles são índices para `message.account_keys`.
                                # `instruction.accounts[0]` -> `message.account_keys[instruction.accounts[0]]` (source)
                                # `instruction.accounts[1]` -> `message.account_keys[instruction.accounts[1]]` (destination)
                                destination_pk_index = instruction.accounts[1]
                                destination_wallet_address = str(msg_accounts[destination_pk_index])

                                amount_bytes = instruction.data[1:9]
                                amount = int.from_bytes(amount_bytes, "little") 
                                
                                # Precisamos saber os decimais do token para converter 'amount' corretamente.
                                # Por simplicidade, vamos assumir 9 decimais como no código original.
                                # Em um bot real, você buscaria os decimais do token.
                                token_decimals = 9 # ASSUMPTION!
                                human_readable_amount = amount / (10**token_decimals)

                                if destination_wallet_address in wallets.get(chat_id, {}).values():
                                    volumes[destination_wallet_address] = volumes.get(destination_wallet_address, 0) + human_readable_amount
                                    logger.debug(f"Transferência para {destination_wallet_address} de {human_readable_amount} tokens")
                            except IndexError:
                                logger.warning(f"Índice de conta inválido na instrução para a assinatura {sig_info.signature}")
                            except Exception as e_instr:
                                logger.error(f"Erro processando instrução para {sig_info.signature}: {e_instr}")
        
        logger.info(f"Processadas {processed_signatures} assinaturas dentro do período da competição.")

        user_volumes = [] # [(user_id, wallet_address, volume)]
        registered_wallets_in_chat = wallets.get(chat_id, {})
        for user_id, wallet_address in registered_wallets_in_chat.items():
            volume = volumes.get(wallet_address, 0)
            if volume > 0: # Apenas incluir quem teve volume
                user_volumes.append((user_id, wallet_address, volume))
        
        if not user_volumes:
            await update.message.reply_text("Nenhum volume de compra registrado para as carteiras participantes no período da competição.")
            return

        user_volumes.sort(key=lambda x: x[2], reverse=True) # Ordenar por volume (maior primeiro)
        
        message = f"🏆 Ranking de Compras - Token {token_address}\n"
        message += f"Período: {start_time.strftime('%d/%m/%Y %H:%M')} - {end_time.strftime('%d/%m/%Y %H:%M')}\n\n"
        
        for i, (user_id, wallet, volume) in enumerate(user_volumes, 1):
            # Tentar obter o nome de usuário do Telegram se possível (requer mais contexto ou acesso ao bot)
            # Por agora, usaremos user_id
            telegram_user = await context.bot.get_chat(user_id) # Tenta buscar dados do usuário
            display_name = telegram_user.username or telegram_user.first_name or str(user_id)

            message += f"{i}. @{display_name}: {volume:.4f} tokens (Carteira: {wallet[:6]}...{wallet[-4:]})\n"
            if i >= 10: # Limitar o ranking exibido para não ficar muito longo
                message += "\nE outros..."
                break
        
        await update.message.reply_text(message)
        logger.info(f"Ranking enviado para o chat {chat_id}")

    except Exception as e:
        logger.error(f"Erro crítico ao gerar ranking para o chat {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(f"Ocorreu um erro inesperado ao gerar o ranking. Tente novamente mais tarde. Detalhe: {str(e)}")

# Handler principal para Vercel
async def main(event_data, context): # Renomeado 'event' para 'event_data' para evitar conflito com 'asyncio.Event'
    # Garantir que as variáveis de ambiente críticas estão carregadas
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_TOKEN não está configurado!")
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "body": json.dumps({"error": "Configuração do servidor incompleta: TELEGRAM_TOKEN faltando."})
        }
    if not solana_client:
        logger.critical("Cliente Solana não inicializado devido à falta de QUICKNODE_URL ou erro na inicialização.")
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "body": json.dumps({"error": "Configuração do servidor incompleta: QUICKNODE_URL faltando ou inválida."})
        }

    try:
        logger.info(f"Recebido evento: {event_data}")
        # O corpo do evento da Vercel para uma requisição HTTP POST está em event_data["body"]
        if isinstance(event_data.get("body"), str):
            body_str = event_data["body"]
        else: # Se já for um dict (menos comum para POST direto, mas pode acontecer via API Gateway)
            body_str = json.dumps(event_data.get("body", {}))

        body = json.loads(body_str)
        logger.info(f"Corpo do webhook: {body}")
        
        update = Update.de_json(body, None) # O segundo argumento é o bot, que o Application builder vai criar
        
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        application.add_handler(CommandHandler("registerwallet", register_wallet))
        application.add_handler(CommandHandler("startcomp", start_comp))
        application.add_handler(CommandHandler("ranking", ranking))
        
        # Processa o update
        await application.process_update(update)
        logger.info("Update processado com sucesso.")
        
        return {
            "statusCode": HTTPStatus.OK.value, # Correção: usar .value
            "body": json.dumps({"status": "ok"})
        }
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao decodificar JSON do corpo da requisição: {e}. Corpo recebido: {event_data.get('body')}")
        return {
            "statusCode": HTTPStatus.BAD_REQUEST.value,
            "body": json.dumps({"error": "Corpo da requisição JSON inválido."})
        }
    except Exception as e:
        logger.error(f"Erro inesperado no handler principal: {e}", exc_info=True)
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value, # Correção: usar .value
            "body": json.dumps({"error": f"Erro interno do servidor: {str(e)}"})
        }

# Entrypoint para Vercel (síncrono)
def handler(event, context):
    logger.info("Handler síncrono chamado pela Vercel.")
    return asyncio.run(main(event, context))
