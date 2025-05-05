import requests
import datetime
import re
import os
from dotenv import load_dotenv
from pytz import utc


load_dotenv()

# Configurações
CLOCKIFY_API_KEY = os.environ.get('CLOCKIFY_API_KEY')
JIRA_API_TOKEN = os.environ.get('JIRA_API_TOKEN')
JIRA_USER_EMAIL = 'kauan.k@widelab.com.br'
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
    """Formata datas para o padrão da API Clockify (YYYY-MM-DDTHH:MM:SSZ)"""
    return data.astimezone(utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def extrair_issue_key(descricao: str) -> str:
    """Extrai a chave do Jira da descrição usando regex"""
    padrao = re.compile(r"([A-Za-z]+-\d+)")  # Aceita letras maiúsculas e minúsculas
    match = padrao.search(descricao or '')
    return match.group(1) if match else None

def dividir_intervalo(inicio: datetime.datetime, fim: datetime.datetime) -> list:
    """Divide um intervalo de tempo em segmentos diários"""
    segmentos = []
    cursor = inicio
    
    while cursor < fim:
        # Calcular fim do dia
        fim_dia = (cursor + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        # Determinar fim real do segmento
        fim_segmento = min(fim, fim_dia)
        
        segmentos.append((cursor, fim_segmento))
        
        # Avançar para o próximo dia
        cursor = fim_segmento
    
    return segmentos

# ==============================================
# INTEGRAÇÃO COM APIs
# ==============================================
def obter_entradas_clockify(workspace_id: str, user_id: str, ultimo_processamento: datetime.datetime):
    """Obtém entradas do Clockify após o último horário processado"""
    agora = datetime.datetime.now(utc)
    
    # Garantir que não vamos para o futuro
    if ultimo_processamento > agora:
        ultimo_processamento = agora - datetime.timedelta(hours=24)
        
    # Ajustar período máximo de consulta (7 dias)
    if (agora - ultimo_processamento).days > 7:
        ultimo_processamento = agora - datetime.timedelta(days=7)
    
    params = {
        'start': formatar_data_api(ultimo_processamento),
        'end': formatar_data_api(agora)
    }
    
    print(f"\n🔍 Buscando entradas no Clockify com parâmetros:")
    print(f"   Início: {params['start']}")
    print(f"   Fim:    {params['end']}")
    
    try:
        response = requests.get(
            f"https://api.clockify.me/api/v1/workspaces/{workspace_id}/user/{user_id}/time-entries",
            headers={'X-Api-Key': CLOCKIFY_API_KEY},
            # params=params,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"⚠️ Erro na API Clockify: {response.status_code}")
            print(f"   Mensagem: {response.text[:200]}...")
            return []
            
        return response.json()
        
    except Exception as e:
        print(f"🔥 Erro de conexão: {str(e)}")
        return []

def criar_worklog_jira(issue_key: str, inicio: datetime.datetime, duracao_segundos: int, descricao: str) -> bool:
    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue/{issue_key}/worklog"
    
    payload = {
        "comment": descricao,
        "started": inicio.strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
        "timeSpentSeconds": int(duracao_segundos)
    }
    
    try:
        response = requests.post(
            url,
            json=payload,
            auth=(JIRA_USER_EMAIL, JIRA_API_TOKEN),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        if response.status_code == 201:
            print(f"✅ Worklog criado para {issue_key} em {inicio.date()}")
            return True
            
        print(f"⛔ Erro ao criar worklog: {response.status_code}")
        print(f"   Detalhes: {response.text[:200]}...")
        return False
        
    except Exception as e:
        print(f"🔥 Erro de conexão: {str(e)}")
        return False


# ==============================================
# EXECUÇÃO PRINCIPAL
# ==============================================
def main():
    print("\n🚀 Iniciando integração Clockify → Jira")
    
    # Verificação inicial de credenciais
    if CLOCKIFY_API_KEY.startswith('sua_api_key'):
        print("❌ Configure sua CLOCKIFY_API_KEY!")
        return
    
    # Obter informações do usuário Clockify
    try:
        usuario = requests.get(
            'https://api.clockify.me/api/v1/user',
            headers={'X-Api-Key': CLOCKIFY_API_KEY},
            timeout=10
        ).json()
    except Exception as e:
        print(f"⛔ Erro ao obter usuário: {str(e)}")
        return
    
    if not usuario:
        print("❌ Falha na autenticação do Clockify")
        return
    
    # Configurar parâmetros iniciais
    workspace_id = usuario['activeWorkspace']
    user_id = usuario['id']
    ultimo_processamento = ler_ultimo_processamento()

    print(workspace_id, user_id)
    
    print(f"\n🕒 Último processamento válido: {ultimo_processamento.isoformat()}")
    
    # Obter entradas do Clockify
    entradas = obter_entradas_clockify(workspace_id, user_id, ultimo_processamento)
    print(f"📥 Entradas encontradas: {len(entradas)}")
    
    novo_ultimo_processamento = ultimo_processamento
    
    # Processar cada entrada
    for entrada in entradas:
        print(f"\n🔨 Processando entrada: {entrada.get('id', 'sem-ID')}")
        
        # Verificar se a entrada está completa
        intervalo = entrada.get('timeInterval', {})
        if not intervalo.get('end'):
            print("⏳ Entrada ainda em andamento. Pulando...")
            continue
            
        try:
            # Converter datas para UTC
            inicio = datetime.datetime.fromisoformat(
                intervalo['start'].replace('Z', '+00:00')
            ).astimezone(utc)
            
            fim = datetime.datetime.fromisoformat(
                intervalo['end'].replace('Z', '+00:00')
            ).astimezone(utc)
        except Exception as e:
            print(f"⚠️ Erro ao converter datas: {str(e)}")
            continue
        
        # Atualizar último processamento
        if fim > novo_ultimo_processamento:
            novo_ultimo_processamento = fim
        
        # Extrair issue key
        issue_key = extrair_issue_key(entrada.get('description', ''))
        if not issue_key:
            print("📭 Nenhum issue key encontrado na descrição")
            continue
            
        # Dividir em períodos diários
        segmentos = dividir_intervalo(inicio, fim)
        print(f"📆 Segmentos diários: {len(segmentos)}")
        
        # Criar worklogs para cada segmento
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
                descricao=entrada.get('description', '')
            )
            
            if sucesso:
                print(f"✔️ Worklog registrado com sucesso")
    
    # Atualizar último processamento
    salvar_ultimo_processamento(novo_ultimo_processamento)
    print(f"\n🎉 Processamento concluído! Último horário processado: {novo_ultimo_processamento.isoformat()}")

if __name__ == "__main__":
    main()