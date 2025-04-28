from flask import Flask, request, jsonify
import requests
import datetime

app = Flask(__name__)

@app.route('/apontar', methods=['POST'])
def apontar():
    data = request.json
    issue_key = data.get('issue_key')
    api_key = data.get('clockify_api_key')

    if not issue_key or not api_key:
        return jsonify({"status": "error", "message": "Faltando dados"}), 400

    # Exemplo de payload para Clockify
    payload = {
        "description": f"Apontamento automático - {issue_key}",
        "start": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        "billable": True
    }

    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json"
    }

    # Exemplo: você deve ajustar para seu workspace e user_id
    workspace_id = "SEU_WORKSPACE_ID"
    user_id = "SEU_USER_ID"
    url = f"https://api.clockify.me/api/v1/workspaces/{workspace_id}/user/{user_id}/time-entries"

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 201:
        return jsonify({"status": "ok"})
    else:
        return jsonify({"status": "erro", "detalhes": response.text}), response.status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
