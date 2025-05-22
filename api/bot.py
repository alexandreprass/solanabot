import json
import os
from datetime import datetime, timedelta
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

# Configurações
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8162370248:AAGAKhkdPBSusC4yXt67UGEmmkFUxDyjU4s")
QUICKNODE_URL = os.environ.get("QUICKNODE_URL", "https://dry-flashy-reel.solana-mainnet.quiknode.pro/9e6485b3ea793670ad44d83380549b176d6ab7db/")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

# Armazenamento em memória
competitions = {}
wallets = {}

# Conexão com QuickNode
solana_client = Client(QUICKNODE_URL)

# Registrar carteira
async def register_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(f"Erro: Endereço inválido. {str(e)}")

# Iniciar competição
async def start_comp(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(f"Erro: {str(e)}")

# Consultar transações e gerar ranking
async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        signatures = solana_client.get_signatures_for_address(token_pubkey, limit=50).value

        volumes = {}
        for sig in signatures:
            tx_time = datetime.fromtimestamp(sig.block_time)
            if start_time <= tx_time <= end_time:
                tx = solana_client.get_transaction(sig.signature).value
                if not tx:
                    continue
                for instruction in tx.transaction.message.instructions:
                    if instruction.program_id == TOKEN_PROGRAM_ID:
                        if instruction.data[0] == 3:
                            accounts = instruction.accounts
                            destination = str(accounts[1])
                            amount = int.from_bytes(instruction.data[1:9], "little") / 1e9
                            if destination in wallets.get(chat_id, {}).values():
                                if destination in volumes:
                                    volumes[destination] += amount
                                else:
                                    volumes[destination] = amount

        user_volumes = [(user_id, wallet, volumes[wallet]) for user_id, wallet in wallets.get(chat_id, {}).items() if wallet in volumes]
        if not user_volumes:
            await update.message.reply_text("Nenhum volume registrado para as carteiras participantes.")
            return

        user_volumes.sort(key=lambda x: x[2], reverse=True)
        message = f"🏆 Ranking de Compras - Token {token_address}\n\n"
        for i, (user_id, wallet, volume) in enumerate(user_volumes, 1):
            message += f"{i}. Usuário {user_id}: {volume:.2f} tokens (Carteira: {wallet[:8]}...)\n"
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Erro ao gerar ranking: {str(e)}")

# Handler para Vercel
async def handler(event, context):
    try:
        body = json.loads(event["body"])
        update = Update.de_json(body, None)
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("registerwallet", register_wallet))
        app.add_handler(CommandHandler("startcomp", start_comp))
        app.add_handler(CommandHandler("ranking", ranking))
        await app.process_update(update)
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok"})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
