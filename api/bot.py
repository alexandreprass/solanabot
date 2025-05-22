# api/bot.py (Versão de Diagnóstico para isolar PTB)
import os
import sys
import json

print("--- INÍCIO DO SCRIPT DE DIAGNÓSTICO (ISOLANDO PTB v13.15) ---")

print(f"Current working directory: {os.getcwd()}")

print("\n--- Conteúdo da Raiz da Função Vercel (/var/task/) ---")
try:
    root_contents = os.listdir("/var/task/")
    print(root_contents)
    if 'telegram' in root_contents:
        print("!!! ALERTA: A PASTA/ARQUIVO 'telegram' AINDA ESTÁ EM /var/task/ !!!")
        telegram_path_suspeito = "/var/task/telegram"
        if os.path.isdir(telegram_path_suspeito):
            print(f"Conteúdo de '{telegram_path_suspeito}' (se for diretório): {os.listdir(telegram_path_suspeito)}")
        else:
            print(f"'{telegram_path_suspeito}' é um arquivo ou outro tipo.")
    else:
        print("--- Pasta/arquivo 'telegram' NÃO encontrada em /var/task/ ---")
except Exception as e_root:
    print(f"Erro ao listar /var/task/: {e_root}")

print("\n--- Python sys.path (Caminhos de Importação) ---")
print(sys.path)

print("\n--- Tentando importar 'telegram' ---")
try:
    import telegram
    print(f"SUCESSO ao importar 'telegram'.")
    print(f"Localização de 'telegram' (telegram.__file__): {telegram.__file__ if hasattr(telegram, '__file__') else 'N/A - __file__ não disponível'}")

    # Tenta importar algo específico da v13.x para ver se é a versão correta
    from telegram.ext import Dispatcher
    print("SUCESSO ao importar 'Dispatcher' de 'telegram.ext'. Parece ser a v13.x correta de site-packages!")

except ImportError as e_import:
    print(f"ERRO ao importar 'telegram' ou seus componentes: {e_import}")
except Exception as e_geral:
    print(f"Outro ERRO durante a importação: {e_geral}")

print("\n--- FIM DO SCRIPT DE DIAGNÓSTICO ---")

def handler(event, context):
    print("Função handler de diagnóstico chamada.")
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Diagnóstico de arquivos (isolando PTB) executado. Verifique os logs.'})
    }
