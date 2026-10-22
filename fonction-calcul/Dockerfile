# Contexte = racine du monorepo : docker build -f fonction-calcul/Dockerfile .
FROM mcr.microsoft.com/azure-functions/python:4-python3.12

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true

COPY fonction-calcul/requirements.txt /home/site/wwwroot/
RUN pip install --no-cache-dir -r /home/site/wwwroot/requirements.txt

COPY fonction-calcul/host.json fonction-calcul/function_app.py /home/site/wwwroot/
COPY fonction-calcul/agentinsurflow_calcul /home/site/wwwroot/agentinsurflow_calcul

# Versions servies par /api/sante, gravées au build (SHA du commit)
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
