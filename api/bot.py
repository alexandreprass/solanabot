# api/bot.py (Versão de Diagnóstico Mínima)
import os
import sys
import json # Apenas para o retorno do handler

print("--- INÍCIO DO SCRIPT DE DIAGNÓSTICO DE ARQUIVOS (PTB REMOVIDO DE REQUIREMENTS) ---")

print(f"Current working directory: {os.getcwd()}")

print("\n--- Conteúdo da Raiz da Função Vercel (/var/task/) ---")
try:
    root_contents = os.listdir("/var/task/")
    print(root_contents)
    if 'telegram' in root_contents:
        print("!!! ALERTA: A PASTA/ARQUIVO 'telegram' AINDA ESTÁ EM /var/task/ MESMO SEM 'python-telegram-bot' NO REQUIREMENTS.TXT !!!")

        # Tenta inspecionar um pouco mais se ainda estiver lá
        telegram_path_suspeito = "/var/task/telegram"
        if os.path.isdir(telegram_path_suspeito):
            print(f"Conteúdo de '{telegram_path_suspeito}' (se for diretório):")
            try:
                print(os.listdir(telegram_path_suspeito))
            except Exception as e_list_tg_suspeito:
                print(f"Erro ao listar conteúdo de '{telegram_path_suspeito}': {e_list_tg_suspeito}")
        elif os.path.isfile(telegram_path_suspeito):
             print(f"'{telegram_path_suspeito}' é um ARQUIVO.")
        else:
            print(f"'{telegram_path_suspeito}' não é diretório nem arquivo.")
    else:
        print("--- PASTA/ARQUIVO 'telegram' NÃO FOI ENCONTRADA EM /var/task/ (bom sinal após remover de requirements.txt) ---")

except Exception as e_root:
    print(f"Erro ao listar /var/task/: {e_root}")

print("\n--- Python sys.path (Caminhos de Importação) ---")
print(sys.path)

print("\n--- FIM DO SCRIPT DE DIAGNÓSTICO DE ARQUIVOS ---")

# Handler mínimo para a Vercel chamar e para podermos ver os prints acima nos logs
def handler(event, context):
    print("Função handler de diagnóstico chamada.")
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Diagnóstico de arquivos executado. Verifique os logs da Vercel.'})
    }
