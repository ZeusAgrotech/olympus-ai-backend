import argparse
import sys
import os
import shutil
import subprocess

# Add parent directory to path to allow importing from security module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.api_keys import create_api_key, list_api_keys, delete_api_key, delete_all_api_keys, generate_key

GCP_SECRET_NAME = os.environ.get('GCP_SECRET_NAME', 'OLYMPUS_AUTH_API_KEY')
GCP_PROJECT = os.environ.get('GCP_PROJECT', '')


def _gcloud_cmd():
    return 'gcloud.cmd' if sys.platform == 'win32' else 'gcloud'


def _check_gcloud():
    if not shutil.which(_gcloud_cmd()):
        print("❌ gcloud CLI não encontrado. Instale em: https://cloud.google.com/sdk/docs/install")
        sys.exit(1)
    project = GCP_PROJECT or subprocess.run(
        [_gcloud_cmd(), 'config', 'get-value', 'project'],
        capture_output=True, text=True
    ).stdout.strip()
    if not project:
        print("❌ Projeto GCP não configurado. Use: gcloud config set project <PROJECT_ID>")
        print("   Ou defina a variável de ambiente GCP_PROJECT.")
        sys.exit(1)
    return project


def create_key_for_gcp(name: str, project: str, secret_name: str) -> str:
    """Cria uma chave e adiciona ao GCP Secret Manager."""
    raw_key = generate_key()

    # Lê o valor atual do secret
    result = subprocess.run(
        [_gcloud_cmd(), 'secrets', 'versions', 'access', 'latest',
         f'--secret={secret_name}', f'--project={project}'],
        capture_output=True, text=True
    )
    current = result.stdout.strip() if result.returncode == 0 else ''

    # Monta nova lista de chaves
    keys = [k for k in current.split(',') if k.strip()]
    keys.append(raw_key)
    new_value = ','.join(keys)

    # Cria nova versão do secret
    proc = subprocess.run(
        [_gcloud_cmd(), 'secrets', 'versions', 'add', secret_name,
         f'--project={project}', '--data-file=-'],
        input=new_value, capture_output=True, text=True
    )
    if proc.returncode != 0:
        print(f"❌ Erro ao atualizar secret: {proc.stderr}")
        sys.exit(1)

    return raw_key


def main():
    parser = argparse.ArgumentParser(description="Gerenciador de Chaves de API")
    parser.add_argument('--gcp', '-G', action='store_true',
                        help='Cria a chave no GCP Secret Manager (para Cloud Run)')
    subparsers = parser.add_subparsers(dest='command', help='Comando a executar')

    # Comando create
    create_parser = subparsers.add_parser('create', help='Criar nova chave')
    create_parser.add_argument('name', help='Nome do cliente/usuário')
    create_parser.add_argument('date', nargs='?', help='Data de validade (YYYY-MM-DD ou DD-MM-YYYY)')

    # Comando list
    subparsers.add_parser('list', help='Listar todas as chaves')

    # Comando delete
    delete_parser = subparsers.add_parser('delete', help='Deletar uma chave pelo ID')
    delete_parser.add_argument('id', type=int, help='ID da chave a ser deletada')

    # Comando delete-all
    subparsers.add_parser('delete-all', help='Deletar TODAS as chaves (com confirmação)')

    args = parser.parse_args()

    if args.command == 'create':
        try:
            if args.gcp:
                project = _check_gcloud()
                key = create_key_for_gcp(args.name, project, GCP_SECRET_NAME)
                print(f"\n✅ Chave criada e adicionada ao GCP Secret Manager para '{args.name}'!")
                print(f"🔑 Chave: {key}")
                print(f"☁️  Secret: {GCP_SECRET_NAME} (projeto: {project})")
                print("⚠️  ATENÇÃO: Copie esta chave agora. Ela não será mostrada novamente.\n")
            else:
                key = create_api_key(args.name, args.date)
                print(f"\n✅ Chave criada com sucesso para '{args.name}'!")
                print(f"🔑 Chave: {key}")
                print("⚠️  ATENÇÃO: Copie esta chave agora. Ela não será mostrada novamente.\n")
                if args.date:
                    print(f"📅 Validade até: {args.date}")
        except Exception as e:
            print(f"❌ Erro ao criar chave: {e}")
            sys.exit(1)

    elif args.command == 'list':
        keys = list_api_keys()
        if not keys:
            print("Nenhuma chave encontrada.")
        else:
            print(f"{'ID':<5} {'NOME':<20} {'PREFIXO':<10} {'CRIADA EM':<20} {'VALIDADE':<20}")
            print("-" * 80)
            for k in keys:
                valid = k['valid_until'] if k['valid_until'] else "Nunca"
                created = k['created_at'].split('.')[0] if k['created_at'] else "?"
                print(f"{k['id']:<5} {k['name']:<20} {k['prefix']:<10} {created:<20} {valid:<20}")

    elif args.command == 'delete':
        if delete_api_key(args.id):
            print(f"✅ Chave ID {args.id} deletada com sucesso.")
        else:
            print(f"❌ Chave ID {args.id} não encontrada.")
            sys.exit(1)

    elif args.command == 'delete-all':
        keys = list_api_keys()
        if not keys:
            print("Nenhuma chave encontrada para deletar.")
        else:
            print(f"⚠️  ATENÇÃO: Você está prestes a deletar {len(keys)} chave(s)!")
            print("Esta ação é IRREVERSÍVEL.")
            confirm = input("Digite 'DELETAR TUDO' para confirmar: ")
            if confirm == 'DELETAR TUDO':
                deleted_count = delete_all_api_keys()
                print(f"✅ {deleted_count} chave(s) deletada(s) com sucesso.")
            else:
                print("❌ Operação cancelada.")
                sys.exit(1)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
