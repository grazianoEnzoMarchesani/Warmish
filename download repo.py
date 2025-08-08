import os
import requests
from git import Repo
import time

# Configurazione
username = "grazianoEnzoMarchesani"
local_base_path = "/Users/grazianoenzomarchesani/Documents/GitHub"
# Inserisci qui il tuo token GitHub se necessario
github_token = None

# Configurazione headers
headers = {}
if github_token:
    headers['Authorization'] = f'token {github_token}'

def get_all_repos(username, headers):
    repos = []
    page = 1
    per_page = 100
    
    while True:
        api_url = f"https://api.github.com/users/{username}/repos?page={page}&per_page={per_page}"
        response = requests.get(api_url, headers=headers)
        
        if response.status_code != 200:
            print(f"Errore nell'accesso all'API: {response.status_code}")
            break
            
        current_repos = response.json()
        if not current_repos:
            break
            
        repos.extend(current_repos)
        
        # Controlla se ci sono altre pagine
        if 'next' not in response.links:
            break
            
        page += 1
        # Rispetta i limiti di rate
        time.sleep(1)
    
    return repos

def update_or_clone_repo(repo_name, repo_url, local_path):
    try:
        if os.path.exists(local_path):
            print(f"Aggiornamento di {repo_name}...")
            repo = Repo(local_path)
            origin = repo.remotes.origin
            origin.pull()
            print(f"Repository {repo_name} aggiornato con successo!")
        else:
            print(f"Clonazione di {repo_name}...")
            Repo.clone_from(repo_url, local_path)
            print(f"Repository {repo_name} clonato con successo!")
    except Exception as e:
        print(f"Errore durante la gestione del repository {repo_name}: {str(e)}")

# Crea la directory base se non esiste
if not os.path.exists(local_base_path):
    os.makedirs(local_base_path)

# Ottieni tutti i repository
print(f"Recupero la lista dei repository per l'utente {username}...")
repos = get_all_repos(username, headers)
print(f"Trovati {len(repos)} repository.")

# Clona o aggiorna ogni repository
for repo in repos:
    repo_name = repo['name']
    repo_url = repo['clone_url']
    local_path = os.path.join(local_base_path, repo_name)
    update_or_clone_repo(repo_name, repo_url, local_path)

print("Operazione completata!")
