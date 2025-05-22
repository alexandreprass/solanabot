import json
import os
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN # Usar Decimal para precisão financeira
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

# --- Configurações Hardcodificadas ---
TELEGRAM_TOKEN = "8162370248:AAGAKhkdPBSusC4yXt67UGEmmkFUxDyjU4s"
QUICKNODE_URL = "https://dry-flashy-reel.solana-mainnet.quiknode.pro/9e6485b3ea793670ad44d83380549b176d6ab7db/"
# ------------------------------------

# Armazenamento em memória para competições
competitions = {}  # {chat_id: {"token_address": str, "start_time": datetime, "period_days": int}}

# Conexão com QuickNode
solana_client = None # Inicializa como None
if QUICKNODE_URL:
    try:
        solana_client = Client(QUICKNODE_URL)
        logger.info("Conexão com QuickNode estabelecida com sucesso usando URL hardcodificada.")
    except Exception as e:
        logger.error(f"Erro ao inicializar cliente Solana com URL hardcodificada: {e}")
        # solana_client permanece None se a conexão falhar
else:
    logger.error("QUICKNODE_URL está vazia (verifique o código).")


async def start_comp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Comando /startcomp recebido de {update.message.from_user.id}")
    chat_id = str(update.message.chat_id)
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Use: /startcomp <endereço_do_token_alvo> <período_em_dias>")
        return
    token_address_str, period_str = args
    try:
        Pubkey.from_string(token_address_str) # Valida endereço do token
        period_days = int(period_str.replace("d", ""))
        
        competitions[chat_id] = {
            "token_address": token_address_str,
            "start_time": datetime.now(),
            "period_days": period_days
        }
        await update.message.reply_text(f"Competição de gastos de SOL iniciada para o token {token_address_str} por {period_days} dias!")
        logger.info(f"Competição (SOL gasta) iniciada no chat {chat_id} para o token {token_address_str} por {period_days} dias.")
    except ValueError:
        logger.error(f"Período inválido fornecido: {period_str}")
        await update.message.reply_text("Erro: O período deve ser um número (ex: '7d' para 7 dias).")
    except Exception as e:
        logger.error(f"Erro ao iniciar competição para token {token_address_str}: {e}")
        await update.message.reply_text(f"Erro ao iniciar competição: {str(e)}")


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Comando /ranking (SOL gasta) recebido de {update.message.from_user.id}")
    chat_id = str(update.message.chat_id)

    if not solana_client:
        logger.error("Cliente Solana não está disponível para o comando ranking.")
        await update.message.reply_text("Erro interno: Serviço Solana indisponível.")
        return

    if chat_id not in competitions:
        await update.message.reply_text("Nenhuma competição ativa neste grupo.")
        return
        
    comp = competitions[chat_id]
    target_token_address_str = comp["token_address"] # O token que queremos ver ser comprado
    target_token_pubkey = Pubkey.from_string(target_token_address_str)
    start_time = comp["start_time"]
    period_days = comp["period_days"]
    end_time = start_time + timedelta(days=period_days)

    if datetime.now() > end_time:
        await update.message.reply_text("A competição terminou!")
        return

    await update.message.reply_text("Calculando ranking de SOL gasta, isso pode levar alguns minutos...")

    sol_spent_by_wallet = {} # {wallet_address_comprador: total_sol_gasta_Decimal}
    SOL_DECIMALS = 9 

    try:
        signatures_response = solana_client.get_signatures_for_address(
            target_token_pubkey,
            limit=200 
        )
        signatures = signatures_response.value if signatures_response else []
        logger.info(f"Obtidas {len(signatures)} assinaturas candidatas envolvendo o token {target_token_address_str}")

        processed_tx_count_in_period = 0
        for sig_info in signatures:
            if sig_info.block_time is None:
                continue
            
            tx_time = datetime.fromtimestamp(sig_info.block_time)
            if not (start_time <= tx_time <= end_time):
                continue
            
            processed_tx_count_in_period +=1
            logger.info(f"Processando transação {sig_info.signature} ({processed_tx_count_in_period} no período)")

            try:
                transaction_detail_response = solana_client.get_transaction(
                    sig_info.signature, 
                    max_supported_transaction_version=0
                )
                tx_info = transaction_detail_response.value if transaction_detail_response else None

                if not tx_info or not tx_info.meta or not tx_info.transaction or not tx_info.transaction.message:
                    logger.warning(f"Metadados ou detalhes da transação faltando para {sig_info.signature}")
                    continue

                account_keys = tx_info.transaction.message.account_keys
                if not account_keys:
                    continue
                
                potential_buyer_pubkey = account_keys[0]
                potential_buyer_address_str = str(potential_buyer_pubkey)

                sol_spent_lamports_for_tx = Decimal(0)
                if tx_info.meta.pre_balances and tx_info.meta.post_balances and \
                   len(tx_info.meta.pre_balances) > 0 and len(tx_info.meta.post_balances) > 0:
                    
                    sol_before_lamports = Decimal(tx_info.meta.pre_balances[0])
                    sol_after_lamports = Decimal(tx_info.meta.post_balances[0])
                    sol_diff_lamports = sol_before_lamports - sol_after_lamports
                    
                    if sol_diff_lamports > 0:
                        sol_spent_lamports_for_tx = sol_diff_lamports
                
                if sol_spent_lamports_for_tx <= 0:
                    continue

                target_token_received_by_buyer = False
                if tx_info.meta.post_token_balances:
                    for post_tk_balance_entry in tx_info.meta.post_token_balances:
                        if post_tk_balance_entry.mint == target_token_address_str and \
                           post_tk_balance_entry.owner == potential_buyer_address_str:

                            pre_tk_balance_entry = next(
                                (pre_b for pre_b in (tx_info.meta.pre_token_balances or [])
                                 if pre_b.account_index == post_tk_balance_entry.account_index and \
                                    pre_b.mint == target_token_address_str),
                                None
                            )
                            
                            amount_after_raw = Decimal(post_tk_balance_entry.ui_token_amount.amount if post_tk_balance_entry.ui_token_amount else '0')
                            amount_before_raw = Decimal(0)
                            if pre_tk_balance_entry and pre_tk_balance_entry.ui_token_amount:
                                amount_before_raw = Decimal(pre_tk_balance_entry.ui_token_amount.amount)
                            
                            if amount_after_raw > amount_before_raw:
                                target_token_received_by_buyer = True
                                break
                
                if target_token_received_by_buyer:
                    sol_spent_native = sol_spent_lamports_for_tx / (Decimal(10)**SOL_DECIMALS)
                    current_total_sol_spent = sol_spent_by_wallet.get(potential_buyer_address_str, Decimal(0))
                    sol_spent_by_wallet[potential_buyer_address_str] = current_total_sol_spent + sol_spent_native
                    logger.info(f"Carteira {potential_buyer_address_str} gastou ~{sol_spent_native:.{SOL_DECIMALS}f} SOL. Total: {sol_spent_by_wallet[potential_buyer_address_str]}")
                else:
                    logger.debug(f"Tx {sig_info.signature}: SOL gasto por {potential_buyer_address_str} mas sem recebimento do token alvo por ele.")

            except Exception as e_tx_proc:
                logger.error(f"Erro processando detalhes da transação {sig_info.signature}: {e_tx_proc}", exc_info=False)

        if not sol_spent_by_wallet:
            await update.message.reply_text(f"Nenhuma compra (SOL gasto para obter {target_token_address_str}) foi identificada no período da competição.")
            return

        ranked_wallets = sorted(sol_spent_by_wallet.items(), key=lambda item: item[1], reverse=True)
        
        message = f"🏆 Ranking de Gasto de SOL - Token Adquirido: {target_token_address_str[:6]}...{target_token_address_str[-4:]}\n"
        message += f"Período: {start_time.strftime('%d/%m/%Y %H:%M')} - {end_time.strftime('%d/%m/%Y %H:%M')}\n\n"
        
        for i, (wallet_address, total_sol_spent) in enumerate(ranked_wallets, 1):
            sol_display = total_sol_spent.quantize(Decimal('0.00001'), rounding=ROUND_DOWN) if total_sol_spent > Decimal(0) else Decimal(0)
            message += f"{i}. Carteira: {wallet_address[:6]}...{wallet_address[-4:]} -> {sol_display} SOL\n"
            if i >= 20:
                message += f"\nE mais {len(ranked_wallets) - i} outras carteiras..."
                break
        
        await update.message.reply_text(message)
        logger.info(f"Ranking de SOL gasta enviado para o chat {chat_id}")

    except Exception as e:
        logger.error(f"Erro crítico ao gerar ranking de SOL gasta para o chat {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(f"Ocorreu um erro inesperado ao gerar o ranking. Detalhe: {str(e)}")


# Handler principal para Vercel (esta função async def main NÃO será chamada pelo handler de teste abaixo)
async def main(event_data, context):
    if not TELEGRAM_TOKEN:
        logger.critical("Variável de ambiente TELEGRAM_TOKEN não está configurada (hardcoded)!")
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "body": json.dumps({"error": "Configuração do servidor incompleta: TELEGRAM_TOKEN faltando."})
        }
    if not solana_client:
        logger.critical("Cliente Solana não inicializado. Verifique a URL do QuickNode ou erros na inicialização (hardcoded).")
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "body": json.dumps({"error": "Configuração do servidor incompleta: Conexão Solana falhou."})
        }

    try:
        logger.info(f"Handler principal 'main' chamado. Recebido evento: {event_data}")
        if isinstance(event_data.get("body"), str):
            body_str = event_data["body"]
        else:
            body_str = json.dumps(event_data.get("body", {}))

        body = json.loads(body_str)
        logger.info(f"Corpo do webhook decodificado: {body}")
        
        update = Update.de_json(body, None)
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        application.add_handler(CommandHandler("startcomp", start_comp))
        application.add_handler(CommandHandler("ranking", ranking))
        
        await application.process_update(update)
        logger.info("Update processado com sucesso pela aplicação Telegram.")
        
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
        logger.error(f"Erro inesperado no handler principal 'main': {e}", exc_info=True)
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "body": json.dumps({"error": f"Erro interno do servidor: {str(e)}"})
        }

# Entrypoint para Vercel (síncrono) - VERSÃO DE TESTE SUPER SIMPLES
def handler(event, context):
    logger.info("[TESTE DIAGNÓSTICO] Handler síncrono SIMPLIFICADO Vercel chamado.")
    logger.info(f"[TESTE DIAGNÓSTICO] Evento recebido: {json.dumps(event, indent=2)}") # Loga o evento formatado
    
    # Não vamos chamar asyncio.run(main(event, context)) por enquanto.
    # Vamos apenas retornar uma resposta dummy bem formatada.
    
    response_body = {"message": "Resposta do handler de teste simplificado Vercel!"}
    status_code = HTTPStatus.OK.value # Usa .value para garantir que é um inteiro (200)
    
    logger.info(f"[TESTE DIAGNÓSTICO] Retornando resposta dummy: statusCode={status_code}, body={json.dumps(response_body)}")
    
    return {
        "statusCode": status_code,
        "body": json.dumps(response_body),
        "headers": { 
            "Content-Type": "application/json"
        }
    }
