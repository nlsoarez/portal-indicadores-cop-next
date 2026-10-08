# Correções Security Guardian

O bootstrap agora preserva desativação, funções e segmentos dos usuários existentes. Novas contas recebem uma credencial aleatória desconhecida e precisam de provisionamento individual. A senha inicial antiga é recusada no login e não pode ser reutilizada em troca/reset.

Cada execução autenticada valida no banco a atividade da conta e o salt da credencial. Reset/troca gera novo salt e revoga sessões anteriores. Sessões abertas antes desta atualização também precisam entrar novamente. O salt permanece no estado de sessão do servidor, sem envio como token ao navegador.

O login admite cinco tentativas por identificador normalizado por janela fixa de um minuto, compartilhadas no banco entre processos. Tentativas bem-sucedidas também contam. A tabela `auth_attempts` é criada no bootstrap, em SQLite ou no schema privado PostgreSQL, com as mesmas restrições de acesso do restante do schema. Entradas antigas são removidas durante as reservas. Esse controle por conta não substitui proteção de origem no proxy contra ataques distribuídos; uma janela fixa permite até dez tentativas perto de uma virada de minuto.

## Entrada em produção

Faça backup do banco e publique esta versão com o procedimento existente. A criação da tabela é aditiva; confirme a inicialização na VPS. Contas que ainda usam a credencial antiga perderão acesso até receber uma senha individual. Confirme a recuperação de ADMIN por terminal antes de disponibilizar o portal.

No terminal confiável da VPS, com o mesmo ambiente/container e banco usados pelo portal:

```bash
docker compose -f docker-compose.vps.yml -f docker-compose.hostinger.yml run --rm portal python -m src.application.credentials_cli set-password ADMIN
docker compose -f docker-compose.vps.yml -f docker-compose.hostinger.yml run --rm portal python -m src.application.credentials_cli retire-password
```

Adapte o segundo arquivo Compose ao override efetivamente usado no deploy. O primeiro comando pede uma senha temporária individual por entrada oculta. O segundo pede a senha compartilhada antiga por entrada oculta e substitui apenas credenciais ainda correspondentes por valores aleatórios desconhecidos, revogando sessões. Não coloque senhas na linha de comando, em logs ou em commits. Contas afetadas podem receber senhas individuais pelo reset administrativo ou pelo comando `set-password LOGIN`. O CLI não reativa contas nem altera funções.

Depois teste: duas sessões abertas devem perder acesso após reset; conta desativada deve continuar assim após reinício; tentativa acima do limite deve ser negada; login deve voltar a funcionar na janela seguinte; nova senha individual deve exigir troca. Verifique o canal Streamlit e as regras do proxy na VPS.

O CLI exige acesso confiável ao servidor e às credenciais de banco; não é uma rota pública. Não há rotação nem deploy automático neste PR. A remoção da senha do código não elimina seu histórico: a invalidação das credenciais existentes continua necessária.
