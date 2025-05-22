import json
import logging
from http import HTTPStatus

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def handler(event, context):
    logger.info("[ROOT INDEX.PY TEST] Função handler INICIADA.")
    
    event_str = str(event)
    try:
        event_str = json.dumps(event)
    except TypeError:
        logger.info(f"[ROOT INDEX.PY TEST] Evento não é serializável em JSON, logando como string.")
    
    logger.info(f"[ROOT INDEX.PY TEST] Evento recebido: {event_str}")

    status_code_to_return = HTTPStatus.OK.value
    response_body_to_return = {"message": "Handler no ROOT INDEX.PY executado com sucesso!"}
    
    response = {
        "statusCode": status_code_to_return,
        "body": json.dumps(response_body_to_return),
        "headers": {"Content-Type": "application/json"}
    }
    
    logger.info(f"[ROOT INDEX.PY TEST] Retornando resposta: {json.dumps(response)}")
    return response
