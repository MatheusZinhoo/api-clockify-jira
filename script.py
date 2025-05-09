import requests
import datetime
import re
from pytz import utc
import pandas as pd
import traceback

from logger import get_logger


JIRA_DOMAIN = 'widelab.atlassian.net'

logger = get_logger()


def intervalo_hoje_utc() -> tuple[str, str]:
    """
    Retorna uma tupla com duas strings:
        1. Data de hoje, meia-noite;
        2. Data de hoje, 23h59
    """
    agora = datetime.datetime.now(datetime.timezone.utc)
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = inicio + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
    return inicio.isoformat().replace("+00:00", "Z"), fim.isoformat().replace("+00:00", "Z")


def data_atual_formatada():
    """Retorna a data de hoje no formato %Y-%m-%d"""
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')


def extrair_issue_key(descricao: str) -> str:
    """Extrai a chave do Jira da descrição"""
    padrao = re.compile(r"([A-Za-z]+-\d+)")
    match = padrao.search(descricao or '')
    return match.group(1) if match else 'WDDEV-2475'


def dividir_intervalo(inicio: datetime.datetime, fim: datetime.datetime) -> list:
    """Divide um intervalo de tempo em segmentos diários"""
    segmentos = []
    cursor = inicio
    
    while cursor < fim:
        fim_dia = (cursor + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fim_segmento = min(fim, fim_dia)
        segmentos.append((cursor, fim_segmento))
        cursor = fim_segmento
    
    return segmentos


def obter_entradas_clockify(workspace_id: str, user_id: str, clockify_api_key: str):
    """Obtém entradas do Clockify"""
    
    start, end = intervalo_hoje_utc()

    params = {
        'start': start,
        'end': end
    }
    
    logger.debug(f"Buscando entradas no Clockify de {params['start']} até {params['end']}")
    
    try:
        response = requests.get(
            f"https://api.clockify.me/api/v1/workspaces/{workspace_id}/user/{user_id}/time-entries",
            headers={'X-Api-Key': clockify_api_key},
            params=params,
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Erro na API Clockify: {response.status_code} - {response.text[:200]}")
            response.raise_for_status()
            
        if user_id == "681902f51b07fb4bb2d4143c":
            import json
            with open('teste.json', 'w') as f:
                json.dump(response.json(), f, indent=4)

        return response.json()
        
    except Exception as e:
        logger.error(f"Erro de conexão: {traceback.format_exc()}")
        return []


def criar_worklog_jira(issue_key: str, inicio: datetime.datetime, duracao_segundos: int, descricao: str, usuario: str, email: str, jira_api_key: str) -> bool:
    """Cria worklog no Jira atribuído ao usuário real (Matheus)"""

    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/worklog"
    logger.debug(f"Issue extraída: {issue_key}")
    
    payload = {
        "comment": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"text": descricao, "type": "text"}]
                }
            ]
        },
        "started": inicio.strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
        "timeSpentSeconds": int(duracao_segundos)
    }
    
    try:
        response = requests.post(
            url,
            json=payload,
            auth=(email, jira_api_key),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        if response.status_code == 201:
            logger.info(f"Worklog criado para {issue_key} em {inicio.date()} como {usuario}")
            return True
            
        logger.error(f"Erro ao criar worklog: {response.status_code} - {response.text[:200]}")

        return False
        
    except Exception as e:
        logger.error(f"Erro de conexão: {traceback.format_exc()}")
        return False


def worklog_lancado(entrada: str, issue_key: str, email: str, jira_api_key: str):

    url = f"https://widelab.atlassian.net/rest/api/3/issue/{issue_key}/worklog"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(
            url = url,
            auth = (email, jira_api_key),
            headers = headers,
            timeout = 10
        )
        
    except Exception as e:
        logger.error(traceback.format_exc())
        return
    
    if response.status_code != 200:
        logger.error(traceback.format_exc())
        return
    
    data_horario_clockify = datetime.datetime.strptime(entrada["timeInterval"]["start"], "%Y-%m-%dT%H:%M:%SZ")
    data_horario_clockify = data_horario_clockify.replace(tzinfo=datetime.timezone.utc)
    
    response_data = response.json()
    for worklog in response_data["worklogs"]:
        data_horario_worklog = datetime.datetime.strptime(worklog["started"], "%Y-%m-%dT%H:%M:%S.%f%z")
        if data_horario_clockify == data_horario_worklog:
            logger.debug(f"Worklog já lançado")
            return True
        
    return False


def integrar_clockify_jira(usuario: str, clockify_api_key: str, jira_api_key: str, email: str):

    logger.debug(f"Iniciando integração Clockify -> Jira do usuário {usuario}")
    
    # Verificação de credenciais
    if not clockify_api_key:
        logger.error(f"clockify_api_key do usuário {usuario} não cadastrada no arquivo excel!")
        return
    
    # Obter usuário Clockify
    try:
        response = requests.get(
            'https://api.clockify.me/api/v1/user',
            headers={'X-Api-Key': clockify_api_key},
            timeout=10
        )
        response.raise_for_status()

    except Exception as e:
        logger.error(f"Erro ao obter usuário: {traceback.format_exc()}")
        return
        
    usuario_json = response.json()

    if not usuario_json:
        logger.error(f"Erro ao obter usuário Clockify: {response.status_code} - {response.text}")
        return
    
    # Configurações iniciais
    workspace_id = usuario_json['activeWorkspace']
    user_id = usuario_json['id']

    logger.debug(f"Acessando Jira como: {email}")
    logger.info(f"Registrando worklogs como: {usuario}")
    
    # Obter entradas do Clockify
    entradas = obter_entradas_clockify(workspace_id, user_id, clockify_api_key)
    logger.debug(f"Entradas encontradas: {len(entradas)}")
    
    # Processar cada entrada
    for entrada in entradas:
        logger.debug(f"Processando entrada: {entrada.get('id', 'sem-ID')}")

        intervalo = entrada.get('timeInterval', {})
        if not intervalo.get('end'):
            logger.info("Entrada ainda em andamento. Pulando...")
            continue
            
        try:
            inicio = datetime.datetime.fromisoformat(
                intervalo['start'].replace('Z', '+00:00')
            ).astimezone(utc)
            
            fim = datetime.datetime.fromisoformat(
                intervalo['end'].replace('Z', '+00:00')
            ).astimezone(utc)
        except Exception as e:
            logger.error(f"Erro ao converter datas: {str(e)}")
            continue
        
        issue_key = extrair_issue_key(entrada.get('description', ''))
        if not issue_key:
            logger.debug("Nenhum issue key encontrado na descrição")
            continue

        if worklog_lancado(entrada, issue_key, email, jira_api_key):
            continue
            
        segmentos = dividir_intervalo(inicio, fim)
        logger.debug(f"Segmentos diários: {len(segmentos)}")
        
        for seg_inicio, seg_fim in segmentos:
            duracao = (seg_fim - seg_inicio).total_seconds()

            if duracao < 60:
                logger.debug(f"Duração muito curta ({duracao}s). Pulando...")
                continue

            logger.debug(f"Processando: {seg_inicio.time()} → {seg_fim.time()} ({duracao}s)")
            sucesso = criar_worklog_jira(
                issue_key=issue_key,
                inicio=seg_inicio,
                duracao_segundos=duracao,
                descricao=entrada.get('description', ''),
                usuario = usuario,
                email = email,
                jira_api_key = jira_api_key
            )
            
            if sucesso:
                logger.info("Worklog registrado com sucesso")
    
    logger.info(f"Processamento concluído para o usuário {usuario}!")


def main():

    logger.info('Iniciando programa')

    try:
        df = pd.read_excel('tokens.xlsx')
    except Exception as e:
        logger.critical(f"Erro ao ler excel dos tokens: {repr(e)}\n{traceback.format_exc()}")
        return

    for i in df.index:

        # Remover possíveis espaços do final dos dados
        usuario = df.loc[i, "usuario"].strip()
        clockify_api_key = df.loc[i, "clockify_api_key"].strip()
        jira_api_key = df.loc[i, "jira_api_key"].strip()
        email = usuario + "@widelab.com.br"
        
        integrar_clockify_jira(
            usuario = usuario,
            clockify_api_key = clockify_api_key,
            jira_api_key = jira_api_key,
            email = email
        )


if __name__ == "__main__":
    main()
