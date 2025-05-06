import requests
import datetime
import re
import os
from dotenv import load_dotenv
from pytz import utc
import pandas as pd


load_dotenv()

JIRA_DOMAIN = 'widelab.atlassian.net'


def salvar_ultimo_processamento(timestamp: datetime.datetime):
    """Salva o último horário processado em formato ISO"""
    with open('ultimo_processamento.txt', 'w') as f:
        f.write(timestamp.isoformat())

def ler_ultimo_processamento() -> datetime.datetime:
    """Lê o último horário processado ou retorna padrão (24h atrás)"""

    if not os.path.exists('ultimo_processamento.txt'):
        padrao = datetime.datetime.now(utc) - datetime.timedelta(hours=24)
        print(f"Arquivo não encontrado. Usando padrão: {padrao.isoformat()}")
        return padrao
    
    with open('ultimo_processamento.txt', 'r') as f:
        conteudo = f.read().strip()
        try:
            return datetime.datetime.fromisoformat(conteudo).astimezone(utc)
        except ValueError as e:
            print(f"Erro ao ler arquivo: {e}. Usando padrão de 24h atrás.")
            return datetime.datetime.now(utc) - datetime.timedelta(hours=24)

def formatar_data_api(data: datetime.datetime) -> str:
    """Formata datas para o padrão da API Clockify"""
    return data.astimezone(utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def intervalo_hoje_utc():
    agora = datetime.datetime.now(datetime.timezone.utc)
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = inicio + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
    return inicio.isoformat().replace("+00:00", "Z"), fim.isoformat().replace("+00:00", "Z")


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
    
    print(f"\n🔍 Buscando entradas no Clockify de {params['start']} até {params['end']}")
    
    try:
        response = requests.get(
            f"https://api.clockify.me/api/v1/workspaces/{workspace_id}/user/{user_id}/time-entries",
            headers={'X-Api-Key': clockify_api_key},
            params=params,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"⚠️ Erro na API Clockify: {response.status_code} - {response.text[:200]}")
            return []
            
        return response.json()
        
    except Exception as e:
        print(f"🔥 Erro de conexão: {str(e)}")
        return []

def criar_worklog_jira(issue_key: str, inicio: datetime.datetime, duracao_segundos: int, descricao: str, usuario: str, email: str, jira_api_key: str) -> bool:
    """Cria worklog no Jira atribuído ao usuário real (Matheus)"""

    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/worklog"
    print(f"Issue extraída: {issue_key}")
    
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
            print(f"✅ Worklog criado para {issue_key} em {inicio.date()} como {usuario}")
            return True
            
        print(f"⛔ Erro ao criar worklog: {response.status_code} - {response.text[:200]}")

        return False
        
    except Exception as e:
        print(f"🔥 Erro de conexão: {str(e)}")
        return False
    

def data_atual_formatada():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')


def filtrar_entradas_hoje(entradas):

    data_atual = data_atual_formatada()
    entradas_hoje = []
    for entrada in entradas:
        
        intervalo = entrada.get('timeInterval')
        if data_atual in intervalo.get('end'):
            entradas_hoje.append(entrada)

    return entradas_hoje


def integrar_clockify_jira(usuario: str, clockify_api_key: str, jira_api_key: str, email: str):

    print("\n🚀 Iniciando integração Clockify → Jira")
    
    # Verificação de credenciais
    if not clockify_api_key:
        print("❌ Configure sua CLOCKIFY_API_KEY no arquivo excel!")
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
        print(f"⛔ Erro ao obter usuário: {str(e)}")
        return
        
    usuario_json = response.json()

    if not usuario_json:
        print(f"❌ Erro ao obter usuário Clockify: {response.status_code} - {response.text}")
        return
    
    # Configurações iniciais
    workspace_id = usuario_json['activeWorkspace']
    user_id = usuario_json['id']
    ultimo_processamento = ler_ultimo_processamento()

    print(f"\n🕒 Último processamento: {ultimo_processamento.isoformat()}")
    print(f"🔑 Acessando Jira como: {email}")
    print(f"👤 Registrando worklogs como: {usuario}")
    
    # Obter entradas do Clockify
    entradas = obter_entradas_clockify(workspace_id, user_id, clockify_api_key)
    entradas = filtrar_entradas_hoje(entradas)
    print(f"📥 Entradas encontradas: {len(entradas)}")
    
    novo_ultimo_processamento = ultimo_processamento
    
    # Processar cada entrada
    for entrada in entradas:
        print(f"\n🔨 Processando entrada: {entrada.get('id', 'sem-ID')}")
        
        intervalo = entrada.get('timeInterval', {})
        if not intervalo.get('end'):
            print("⏳ Entrada ainda em andamento. Pulando...")
            continue
            
        try:
            inicio = datetime.datetime.fromisoformat(
                intervalo['start'].replace('Z', '+00:00')
            ).astimezone(utc)
            
            fim = datetime.datetime.fromisoformat(
                intervalo['end'].replace('Z', '+00:00')
            ).astimezone(utc)
        except Exception as e:
            print(f"⚠️ Erro ao converter datas: {str(e)}")
            continue
        
        if fim > novo_ultimo_processamento:
            novo_ultimo_processamento = fim
        
        issue_key = extrair_issue_key(entrada.get('description', ''))
        if not issue_key:
            print("📭 Nenhum issue key encontrado na descrição")
            continue
            
        segmentos = dividir_intervalo(inicio, fim)
        print(f"📆 Segmentos diários: {len(segmentos)}")
        
        for seg_inicio, seg_fim in segmentos:
            duracao = (seg_fim - seg_inicio).total_seconds()
            
            if duracao < 60:
                print(f"⏱️ Duração muito curta ({duracao}s). Pulando...")
                continue
                
            print(f"🕓 Processando: {seg_inicio.time()} → {seg_fim.time()} ({duracao}s)")
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
                print("✔️ Worklog registrado com sucesso")
    
    # Atualizar último processamento
    salvar_ultimo_processamento(novo_ultimo_processamento)
    print(f"\n🎉 Processamento concluído! Último horário processado: {novo_ultimo_processamento.isoformat()}")


def main():

    df = pd.read_excel('tokens.xlsx')

    for i in df.index:

        usuario = df.loc[i, "usuario"]
        clockify_api_key = df.loc[i, "clockify_api_key"]
        jira_api_key = df.loc[i, "jira_api_key"]
        email = usuario + "@widelab.com.br"
        
        try:
            integrar_clockify_jira(
                usuario = usuario,
                clockify_api_key = clockify_api_key,
                jira_api_key = jira_api_key,
                email = email
            )
        except Exception as e:
            raise


if __name__ == "__main__":
    main()
