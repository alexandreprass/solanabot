import json
import os
from datetime import datetime, timedelta
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from http import HTTPStatus
import asyncio
import logging

# Configurar logging básico para Vercel
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurações (carregadas no início do módulo)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
QUICKNODE_URL = os.environ.get("QUICKNODE_URL")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

# Armazenamento em memória para competições
# Será resetado entre invocações em ambientes serverless,
# a menos que a instância da função seja reutilizada ("warm start")
competitions = {}  # {chat_id: {"token_address": str, "start_time": datetime, "period_days": int}}

# Conexão com QuickNode
if QUICKNODE_URL:
    try:
        solana_client = Client(QUICKNODE_URL)
        logger.info("Conexão com QuickNode estabelecida com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao inicializar cliente Solana: {e}")
        solana_client = None
else:
    logger.error("QUICKNODE_URL não está configurada como variável de ambiente.")
    solana_client = None

# Iniciar competição (permanece igual)
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

# Consultar transações e gerar ranking (modificado)
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
        # Considere limpar a competição: del competitions[chat_id]
        return

    await update.message.reply_text("Calculando ranking, por favor aguarde...")

    try:
        token_pubkey = Pubkey.from_string(token_address)
        signatures_response = solana_client.get_signatures_for_address(
            token_pubkey,
            limit=150 # Aumentado o limite, ajuste conforme necessário
        )
        signatures = signatures_response.value if signatures_response else []
        logger.info(f"Obtidas {len(signatures)} assinaturas para o token {token_address}")

        # volumes agora armazena {wallet_address_destino: volume_total_recebido}
        volumes = {} 
        processed_signatures_in_period = 0

        for sig_info in signatures:
            if sig_info.block_time is None:
                continue
            
            tx_time = datetime.fromtimestamp(sig_info.block_time)
            if not (start_time <= tx_time <= end_time): # Filtra transações fora do período
                continue
            
            processed_signatures_in_period += 1
            # A chamada get_transaction é custosa. Para um grande volume, considere otimizações.
            transaction_detail = solana_client.get_transaction(sig_info.signature, max_supported_transaction_version=0)
            tx = transaction_detail.value if transaction_detail else None

            if not tx or not tx.transaction or not tx.transaction.message:
                logger.warning(f"Não foi possível obter detalhes da transação para a assinatura: {sig_info.signature}")
                continue

            for instruction in tx.transaction.message.instructions:
                if instruction.program_id == TOKEN_PROGRAM_ID:
                    if len(instruction.data) >= 9 and instruction.data[0] == 3: # Instrução de Transferência
                        msg_accounts = tx.transaction.message.account_keys
                        try:
                            destination_pk_index = instruction.accounts[1] # Índice da conta de destino na tx
                            destination_wallet_address = str(msg_accounts[destination_pk_index])
                            
                            amount_bytes = instruction.data[1:9]
                            amount = int.from_bytes(amount_bytes, "little")
                            
                            # ASSUMINDO 9 DECIMAIS PARA O TOKEN. Idealmente, buscar via RPC.
                            token_decimals = 9 
                            human_readable_amount = amount / (10**token_decimals)

                            # Acumula volume para qualquer carteira de destino que recebeu o token
                            volumes[destination_wallet_address] = volumes.get(destination_wallet_address, 0) + human_readable_amount
                            logger.debug(f"Transferência para {destination_wallet_address} de {human_readable_amount} tokens")
                        except IndexError:
                            logger.warning(f"Índice de conta inválido na instrução para a assinatura {sig_info.signature}")
                        except Exception as e_instr:
                            logger.error(f"Erro processando instrução para {sig_info.signature}: {e_instr}")
        
        logger.info(f"Processadas {processed_signatures_in_period} assinaturas dentro do período da competição.")

        if not volumes:
            await update.message.reply_text("Nenhum volume de tokens (recebimentos) registrado no período da competição.")
            return

        # Prepara os volumes para o ranking (lista de tuplas: (wallet_address, volume))
        ranked_wallets = []
        for wallet_address, volume in volumes.items():
            if volume > 0: # Apenas incluir quem teve volume
                ranked_wallets.append((wallet_address, volume))
        
        if not ranked_wallets: # Dupla verificação, caso volumes contenham apenas zeros (improvável se o if acima funcionar)
            await update.message.reply_text("Nenhum volume de tokens (recebimentos) significativo registrado.")
            return

        ranked_wallets.sort(key=lambda x: x[1], reverse=True) # Ordenar por volume (maior primeiro)
        
        message = f"🏆 Ranking de Recebimento - Token {token_address}\n"
        message += f"Período: {start_time.strftime('%d/%m/%Y %H:%M')} - {end_time.strftime('%d/%m/%Y %H:%M')}\n\n"
        
        for i, (wallet, volume) in enumerate(ranked_wallets, 1):
            message += f"{i}. Carteira: {wallet[:6]}...{wallet[-4:]} -> {volume:.4f} tokens\n"
            if i >= 20: # Limitar o ranking exibido para não ficar muito longo
                message += f"\nE mais {len(ranked_wallets) - i} outras carteiras..."
                break
        
        await update.message.reply_text(message)
        logger.info(f"Ranking enviado para o chat {chat_id}")

    except Exception as e:
        logger.error(f"Erro crítico ao gerar ranking para o chat {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(f"Ocorreu um erro inesperado ao gerar o ranking. Tente novamente mais tarde.")


# Handler principal para Vercel
async def main(event_data, context):
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_TOKEN não está configurado!")
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "body": json.dumps({"error": "Configuração do servidor incompleta: TELEGRAM_TOKEN faltando."})
        }
    if not solana_client:
        logger.critical("Cliente Solana não inicializado.")
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "body": json.dumps({"error": "Configuração do servidor incompleta: Conexão Solana falhou."})
        }

    try:
        logger.info(f"Recebido evento: {event_data}")
        if isinstance(event_data.get("body"), str):
            body_str = event_data["body"]
        else:
            body_str = json.dumps(event_data.get("body", {}))

        body = json.loads(body_str)
        logger.info(f"Corpo do webhook: {body}")
        
        update = Update.de_json(body, None)
        
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # REMOVIDO: application.add_handler(CommandHandler("registerwallet", register_wallet))
        application.add_handler(CommandHandler("startcomp", start_comp))
        application.add_handler(CommandHandler("ranking", ranking))
        
        await application.process_update(update)
        logger.info("Update processado com sucesso.")
        
        return {
            "statusCode": HTTPStatus.OK.value,
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
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "body": json.dumps({"error": f"Erro interno do servidor: {str(e)}"})
        }

# Entrypoint para Vercel (síncrono)
def handler(event, context):
    logger.info("Handler síncrono chamado pela Vercel.")
    return asyncio.run(main(event, context))
