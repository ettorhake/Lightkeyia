# -*- coding: utf-8 -*-
"""Run_Ollama_publicly_with_ngrok.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1B97Y2zlIkiqXM-7iZwNHoWcy2q4m2iu3
"""

!curl -fsSL https://ollama.com/install.sh | sh
!wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
!tar xvzf ngrok-v3-stable-linux-amd64.tgz

from google.colab import userdata
auth_token = userdata.get('NGROK_AUTH_TOKEN')
ngrok_domain = userdata.get('NGROK_DOMAIN')
ollama_model = userdata.get('MODELNAME')

!./ngrok authtoken {auth_token}
!ollama serve & ./ngrok http 11434 --host-header="localhost:11434" --domain={ngrok_domain} --log stdout & sleep 5s && ollama run {ollama_model}