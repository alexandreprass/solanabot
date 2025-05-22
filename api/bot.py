import json
import logging
from http import HTTPStatus # Mantido para consistência, mas poderia ser um inteiro direto

# Configuração mínima de logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def handler(event, context):
    logger.info("[ULTRA SIMPLES TESTE] Função handler INICIADA.")
    
    # Loga o evento recebido para depuração
    try:
        logger.info(f"[ULTRA SIMPLES TESTE] Evento recebido: {json.dumps(event)}")
    except Exception as e:
        logger.info(f"[ULTRA SIMPLES TESTE] Evento recebido (não pôde ser serializado para JSON): {event}, Erro: {e}")

    status_code_to_return = HTTPStatus.OK.value # Garante que é um inteiro (200)
    response_body_to_return = {"message": "Handler ultra-simples executado com sucesso!"}
    
    response = {
        "statusCode": status_code_to_return,
        "body": json.dumps(response_body_to_return),
        "headers": {
            "Content-Type": "application/json"
        }
    }
    
    logger.info(f"[ULTRA SIMPLES TESTE] Retornando resposta: {json.dumps(response)}")
    return response
