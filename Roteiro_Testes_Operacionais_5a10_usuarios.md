# Roteiro de Testes Operacionais (5 a 10 Usuários)

## 1. Objetivo
Validar o comportamento do bot com um grupo pequeno real (5 a 10 pessoas), garantindo:
- Cadastro e monitoramento de produtos
- Atualização de preços
- Geração de alertas
- Resiliência a erros comuns e incomuns
- Visibilidade de operação para admin

## 2. Escopo
Inclui:
- Bot Telegram
- Cadastro e associação usuário-produto
- Refresh de preços
- Monitoring worker
- Notification worker
- Alertas para admin
- Comando administrativo /relatorio

Não inclui:
- Teste de carga massiva (4k+)
- Testes de performance profunda da API da Amazon

## 3. Pré-requisitos
- Banco PostgreSQL local criado e acessível
- Variáveis de ambiente preenchidas no .env
- Bot Telegram ativo com token válido
- ADMIN_TELEGRAM_ID e ADMIN_ALERT_CHAT_ID configurados
- 5 a 10 pessoas com acesso ao bot (cada uma precisa iniciar conversa com /start)

## 4. Dados de Teste (sugestão)
Monte uma planilha simples com:
- Usuário
- Telegram ID
- Nome
- Link Amazon enviado
- Resultado esperado
- Resultado obtido
- Observações

Sugestão de links:
- 4 livros reais com preço visível
- 1 link inválido
- 1 link que não é Amazon
- 1 produto repetido por vários usuários
- 1 item que pode não retornar preço

## 5. Sequência de Execução Recomendada
1. Subir bot
2. Cadastrar usuários com /start
3. Fazer cadastro de produtos (cenário normal)
4. Testar erros de entrada (links inválidos e não Amazon)
5. Testar limite por usuário
6. Rodar refresh e workers
7. Validar alertas e fila de notificações
8. Validar /relatorio com admin e não admin
9. Rodar cenários diferentões
10. Encerrar com checklist de aceite

## 6. Casos de Teste Essenciais

### Caso 1 - Onboarding básico
Passos:
1. Cada usuário envia /start
2. Cada usuário envia /ajuda

Esperado:
- Usuário recebe mensagem de ajuda
- Usuário é registrado no banco
- Não há erro no log

### Caso 2 - Cadastro válido de livro
Passos:
1. Usuário envia /livro
2. Usuário envia link Amazon válido

Esperado:
- Produto cadastrado com sucesso
- Relação usuário-produto criada
- Se preço vier da API, histórico de preço é registrado

### Caso 3 - Mesmo produto para vários usuários
Passos:
1. Usuário A cadastra produto X
2. Usuário B, C, D cadastram o mesmo produto X

Esperado:
- Apenas 1 registro de produto
- Várias relações usuário-produto
- Sem duplicação indevida na tabela de produtos

### Caso 4 - Lista e remoção
Passos:
1. Usuário envia /lista
2. Usuário envia /remover e remove 1 item
3. Usuário envia /lista novamente

Esperado:
- Item removido corretamente da lista daquele usuário
- Produto continua para outros usuários que monitoram o mesmo item

### Caso 5 - Status
Passos:
1. Usuário envia /status
2. Seleciona um produto

Esperado:
- Retorna preço atual se houver histórico
- Retorna mensagem amigável se ainda não houver preço registrado

### Caso 6 - Link inválido
Passos:
1. Usuário envia texto sem URL
2. Usuário envia URL não Amazon (exemplo: google.com)
3. Usuário envia URL quebrada da Amazon

Esperado:
- Mensagem de erro clara
- Nada é cadastrado no banco
- Bot não quebra

### Caso 7 - Limite de produtos por usuário
Passos:
1. Ajustar USER_PRODUCT_MONITOR_LIMIT no .env (exemplo: 2)
2. Usuário tenta cadastrar 3 produtos diferentes

Esperado:
- Terceiro cadastro bloqueado
- Mensagem exibe exatamente o valor configurado

### Caso 8 - /relatorio admin
Passos:
1. Admin envia /relatorio

Esperado:
- Mostra métricas sem erro
- Campos coerentes com o estado do banco

### Caso 9 - /relatorio não admin
Passos:
1. Usuário comum envia /relatorio

Esperado:
- Acesso negado com mensagem adequada

### Caso 10 - Alertas críticos para admin
Passos:
1. Simular erro controlado no sistema (exemplo já usado de erro crítico)

Esperado:
- Admin recebe mensagem com prefixo ERRO LIVROS BOT
- Stack/contexto aparece no alerta

## 7. Casos de Erro e Exceção (obrigatórios)

### Erro A - Amazon indisponível temporariamente
Como testar:
- Desligar rede momentaneamente ou usar credencial inválida em ambiente de teste

Esperado:
- Cadastro ou refresh retorna erro amigável
- Sistema continua funcional para novos comandos
- Sem travamento de worker

### Erro B - Produto sem preço
Como testar:
- Usar item que retorna resposta sem preço

Esperado:
- Produto pode ser cadastrado
- Status indica ausência de preço
- Sem queda de preço falsa

### Erro C - Falha Telegram no envio
Como testar:
- Usuário bloqueia o bot

Esperado:
- Envio falha sem derrubar worker
- Erro registrado
- Admin alertado quando aplicável

### Erro D - Banco indisponível
Como testar:
- Parar Postgres por alguns minutos

Esperado:
- Aplicação acusa erro de conexão
- Sem corrupção de dados
- Retomada normal quando banco volta

## 8. Casos Diferentões (recomendados)

### Diferentão 1 - Produto com monitoramento cruzado
Cenário:
- Usuários A e B monitoram 3 produtos iguais
- Usuário C monitora apenas 1

Validar:
- Relações corretas
- Notificação enviada para todos os usuários daquele produto

### Diferentão 2 - Reenvio do mesmo link muitas vezes
Cenário:
- Mesmo usuário envia o mesmo link 5 vezes

Validar:
- Não cria duplicata de relação
- Mensagem não engana o usuário

### Diferentão 3 - Entrada com parâmetros extras
Cenário:
- Link Amazon com query params longos e tracking

Validar:
- Extração de ASIN continua correta
- Cadastro funciona

### Diferentão 4 - Execução concorrente de refresh + worker
Cenário:
- Rodar refresh enquanto worker está drenando fila

Validar:
- Sem duplicação de jobs pendentes ativos
- Lock de worker respeitado

### Diferentão 5 - Janela de frequência segmentada
Cenário:
- Produto com 3+ usuários monitorando versus produto com 1 usuário

Validar:
- Elegibilidade de refresh respeita janelas configuradas
- Produto high-tier entra mais cedo que low-tier

## 9. Comandos úteis durante o teste
- Subir bot: python .\app\main.py
- Enfileirar refresh: python .\app\services\refresh_prices.py
- Rodar monitoring worker uma vez: python .\app\scheduler\monitoring_worker.py
- Rodar notification worker uma vez: python .\app\scheduler\notification_worker.py

## 10. Critérios de Aceite
A rodada é aprovada se:
- Fluxo feliz completo funciona para 5-10 usuários
- Limite por usuário funciona com valor do .env
- /relatorio funciona para admin e bloqueia não admin
- Erros críticos chegam no canal/admin com prefixo ERRO LIVROS BOT
- Casos inválidos não derrubam aplicação
- Filas são processadas sem duplicação crítica

## 11. Registro de Evidências
Para cada caso, guarde:
- Print da conversa no Telegram
- Trecho de log
- Resultado no banco (quando necessário)
- Status final: Aprovado, Reprovado, Bloqueado

## 12. Pós-rodada
- Consolidar bugs por severidade
- Corrigir severidade alta primeiro
- Reexecutar apenas os casos afetados + fumaça final
