import json
import os
import logging
from datetime import datetime, timedelta
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8162370248:AAGAKhkdPBSusC4yXt67UGEmmkFUxDyjU4s")
QUICKNODE_URL = os.environ.get("QUICKNODE_URL", "https://dry-flashy-reel.solana-mainnet.quiknode.pro/9e6485b3ea793670ad44d83380549b176d6ab7db/")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

# Armazenamento em memória
competitions = {}
wallets = {}

# Conexão com QuickNode
try:
    solana_client = Client(QUICKNODE_URL)
    logger.info("Conexão com QuickNode estabelecida com sucesso")
except Exception as e:
    logger.error(f"Erro ao conectar ao QuickNode: {str(e)}")

# Registrar carteira
async def register_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Executando comando /registerwallet")
    chat_id = str(update.message.chat_id)
    user_id = update.message.from_user.id
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Use: /registerwallet <endereço_da_carteira>")
        return
    wallet_address = args[0]
    try:
        Pubkey.from_string(wallet_address)
        if chat_id not in wallets:
            wallets[chat_id] = {}
        wallets[chat_id][user_id] = wallet_address
        await update.message.reply_text(f"Carteira {wallet_address} registrada com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao registrar carteira: {str(e)}")
        await update.message.reply_text(f"Erro: Endereço inválido ou problema interno. {str(e)}")

# Iniciar competição
async def start_comp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Executando comando /startcomp")
    chat_id = str(update.message.chat_id)
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Use: /startcomp <endereço_do_token> <período_em_dias>")
        return
    token_address, period = args
    try:
        period_days = int(period.replace("d", ""))
        Pubkey.from_string(token_address)
        competitions[chat_id] = {
            "token_address": token_address,
            "start_time": datetime.now(),
            "period_days": period_days
        }
        await update.message.reply_text("⚠️ Aviso: Investir em criptomoedas envolve riscos. Participe por sua conta e risco.")
        await update.message.reply_text(f"Competição iniciada para o token {token_address} por {period_days} dias!")
    except Exception as e:
        logger.error(f"Erro ao iniciar competição: {str(e)}")
        await update.message.reply_text(f"Erro: {str(e)}")

# Consultar transações e gerar ranking
async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Executando comando /ranking")
    chat_id = str(update.message.chat_id)
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
        return

    try:
        token_pubkey = Pubkey.from_string(token_address)
        signatures = solana_client.get_signatures_for_address(token_pubkey, limit=25).value

        volumes = {}
        for sig in signatures:
            if sig.block_time is None:
                continue
            tx_time = datetime.fromtimestamp(sig.block_time)
            if start_time <= tx_time <= end_time:
                tx = solana_client.get_transaction(sig.signature).value
                if not tx:
                    continue
                for instruction in tx.transaction.message.instructions:
                    if instruction.program_id == TOKEN_PROGRAM_ID and len(instruction.data) >= 9:
                        if instruction.data[0] == 3:
                            accounts = instruction.accounts
                            if len(accounts) > 1:
                                destination = str(accounts[1])
                                amount = int.from_bytes(instruction.data[1:9], "little") / 1e9
                                if destination in wallets.get(chat_id, {}).values():
                                    volumes[destination] = volumes.get(destination, 0) + amount

        user_volumes = [(user_id, wallet, volumes.get(wallet, 0)) for user_id, wallet in wallets.get(chat_id, {}).items()]
        user_volumes = [v for v in user_volumes if v[2] > 0]
        if not user_volumes:
            await update.message.reply_text("Nenhum volume registrado para as carteiras participantes.")
            return

        user_volumes.sort(key=lambda x: x[2], reverse=True)
        message = f"🏆 Ranking de Compras - Token {token_address}\n\n"
        for i, (user_id, wallet, volume) in enumerate(user_volumes, 1):
            message += f"{i}. Usuário {user_id}: {volume:.2f} tokens (Carteira: {wallet[:8]}...)\n"
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Erro ao gerar ranking: {str(e)}")
        await update.message.reply_text(f"Erro ao gerar ranking: {str(e)}")

# Handler para Vercel
async def handler(event, context):
    logger.info("Handler chamado com evento: %s", event)
    try:
        body = json.loads(event.get("body", "{}"))
        logger.info("Body recebido: %s", body)
        update = Update.de_json(body, None)
        if update and update.message:
            logger.info("Update válido recebido, processando...")
            app = Application.builder().token(TELEGRAM_TOKEN).build()
            app.add_handler(CommandHandler("registerwallet", register_wallet))
            app.add_handler(CommandHandler("startcomp", start_comp))
            app.add_handler(CommandHandler("ranking", ranking))
            await app.process_update(update)
            logger.info("Update processado com sucesso")
        else:
            logger.warning("Nenhum update válido encontrado no evento")
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok"})
        }
    except Exception as e:
        logger.error("Erro no handler: %s", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

# Para compatibilidade com Vercel
def lambda_handler(event, context):
    logger.info("Lambda handler chamado")
    return asyncio.run(handler(event, context))
