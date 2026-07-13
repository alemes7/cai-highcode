import random
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

from acoes.models import Acao, StatusAcao
from comunicados.models import Comunicado, ContadorCaiFiscal, StatusComunicado, TipoComunicado
from comunicados.services import _prioridade_status, calcular_ano_fiscal
from core.models import Departamento
from tarefas.models import StatusTarefa, Tarefa

User = get_user_model()

# Domínio fictício — nunca usar o domínio real da empresa aqui.
EMAIL_DOMINIO = "ecn-demo.com.br"

DEPARTAMENTOS = [
    "Engenharia", "Qualidade", "TI", "Compras", "Vendas",
    "Logística", "Financeiro", "Manutenção", "Recursos Humanos", "Jurídico",
]

CLIENTES = [
    "Aethra Motors", "Berco Industrial", "Cummins Brasil", "Scania Componentes",
    "GM Powertrain", "Polaris Fabril", "Stellantis Peças", "John Deere Equip.",
    "MBB Sistemas", "CNHi Máquinas",
]

DESFECHOS = ["pendente", "aprovado", "aprovado_com_acoes", "rejeitado", "cancelado"]
PESOS_DESFECHOS = [25, 30, 20, 10, 15]


class Command(BaseCommand):
    help = (
        "Popula o banco com dados fictícios em massa (departamentos, usuários, "
        "comunicados, tarefas e ações) para demonstração. Usa bulk_create/"
        "bulk_update — não passa pela camada de serviço normal (que dispara "
        "e-mail por Tarefa/Ação) porque em volume alto isso seria lento demais "
        "e geraria dezenas de milhares de notificações à toa. Os usuários "
        f"gerados usam o domínio fictício @{EMAIL_DOMINIO} — nunca dados reais. "
        "Rodar com --limpar apaga TODOS os Comunicados/Departamentos existentes "
        "antes de recriar (ação destrutiva e irreversível)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Apaga Comunicados, Departamentos e usuários fictícios existentes antes de recriar.",
        )
        parser.add_argument(
            "--quantidade",
            type=int,
            default=10000,
            help=(
                "Quantos Comunicados fictícios criar (padrão: 10000 — com Tarefas "
                "e Ações em cima, dá uns 40 mil registros no total)."
            ),
        )

    def handle(self, *args, **options):
        self.fake = Faker("pt_BR")

        if options["limpar"]:
            self._limpar()

        usuarios = self._criar_usuarios()
        departamentos = self._criar_departamentos(usuarios)
        total_comunicados, total_tarefas, total_acoes = self._gerar_em_massa(
            options["quantidade"], usuarios, departamentos
        )

        self.stdout.write(self.style.SUCCESS(
            f"Pronto: {len(usuarios)} usuários, {len(departamentos)} departamentos, "
            f"{total_comunicados} comunicados, {total_tarefas} tarefas, {total_acoes} ações "
            f"({total_comunicados + total_tarefas + total_acoes} registros no total)."
        ))
        self.stdout.write("Senha de todos os usuários fictícios: demo12345")

    def _limpar(self):
        self.stdout.write("Removendo dados fictícios anteriores...")
        Comunicado.objects.all().delete()
        Departamento.objects.all().delete()
        User.objects.filter(email__iendswith=f"@{EMAIL_DOMINIO}").delete()

    def _criar_usuarios(self):
        # make_password() é deliberadamente lento (PBKDF2 com muitas iterações,
        # ~0,5-0,7s por chamada) — calcular uma vez só e reaproveitar o mesmo
        # hash pra todo mundo evita 60 chamadas (~40s perdidos à toa, já que
        # todos os usuários fictícios usam a mesma senha de demonstração).
        senha_hash = make_password("demo12345")
        usuarios = []
        for i in range(60):
            nome = self.fake.unique.name()
            partes = nome.replace(".", "").lower().split()
            username = f"{partes[0]}.{partes[-1]}"
            email = f"{username}@{EMAIL_DOMINIO}"
            usuario, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": partes[0].capitalize(),
                    "last_name": " ".join(p.capitalize() for p in partes[1:]),
                    "email": email,
                    "password": senha_hash,
                    # Os 5 primeiros viram administradores da demo (acesso a
                    # Novo Comunicado e Configurações — ver core/decorators.py).
                    "is_staff": i < 5,
                },
            )
            usuarios.append(usuario)
        return usuarios

    def _criar_departamentos(self, usuarios):
        departamentos = []
        for i, nome in enumerate(DEPARTAMENTOS):
            departamento, criado = Departamento.objects.get_or_create(
                nome=nome,
                defaults={"responsavel_obrigatorio": i in (0, 2)},
            )
            if criado:
                responsaveis = random.sample(usuarios, k=random.randint(2, 5))
                departamento.responsaveis.set(responsaveis)
                if random.random() < 0.6:
                    copia = random.sample(usuarios, k=random.randint(1, 2))
                    departamento.responsaveis_copia.set(copia)
            departamentos.append(departamento)
        return departamentos

    def _gerar_em_massa(self, quantidade, usuarios, departamentos):
        hoje = timezone.localdate()
        lote = 1000

        # Responsáveis por departamento, buscados uma única vez (evita N+1
        # nas dezenas de milhares de Tarefas geradas a seguir).
        responsaveis_por_departamento = {
            dept.id: (list(dept.responsaveis.all()) or usuarios) for dept in departamentos
        }

        contadores = {c.ano_fiscal: c.ultimo_numero for c in ContadorCaiFiscal.objects.all()}

        # --- 1) Comunicados -------------------------------------------------
        self.stdout.write(f"Gerando {quantidade} Comunicados...")
        comunicados = []
        for _ in range(quantidade):
            data_criacao = hoje - timedelta(days=random.randint(10, 1500))
            ano_fiscal = calcular_ano_fiscal(data_criacao)
            contadores[ano_fiscal] = contadores.get(ano_fiscal, 0) + 1
            numero_sequencial = contadores[ano_fiscal]

            comunicados.append(Comunicado(
                ano_fiscal=ano_fiscal,
                numero_sequencial=numero_sequencial,
                cai_fiscal=f"{numero_sequencial} / {ano_fiscal}",
                data_criacao=data_criacao,
                data_cai=data_criacao,
                tipo=random.choice(list(TipoComunicado.values)),
                revisao=str(random.randint(0, 25)),
                departamento_solicitante=random.choice(departamentos),
                solicitante=random.choice(usuarios),
                criado_por=random.choice(usuarios),
                cliente=random.choice(CLIENTES),
                numero_projeto=self.fake.bothify(text="???-####").upper(),
                comentarios=self.fake.sentence(nb_words=10),
                status=StatusComunicado.PENDENTE,  # provisório — corrigido no passo 4
            ))

        Comunicado.objects.bulk_create(comunicados, batch_size=lote)
        # auto_now_add ignora o valor setado antes do bulk_create, então
        # sobrescrevemos criado_em de verdade com um bulk_update logo depois.
        for c in comunicados:
            c.criado_em = timezone.make_aware(datetime.combine(c.data_criacao, time(9, 0)))
        Comunicado.objects.bulk_update(comunicados, ["criado_em"], batch_size=lote)

        for ano_fiscal, ultimo in contadores.items():
            ContadorCaiFiscal.objects.update_or_create(
                ano_fiscal=ano_fiscal, defaults={"ultimo_numero": ultimo}
            )

        # --- 2) Tarefas -------------------------------------------------------
        self.stdout.write("Gerando Tarefas...")
        tarefas = []
        tarefas_por_comunicado = {}
        for comunicado in comunicados:
            departamentos_escolhidos = random.sample(
                departamentos, k=random.randint(1, min(4, len(departamentos)))
            )
            desfecho = random.choices(DESFECHOS, weights=PESOS_DESFECHOS)[0]
            comunicado._desfecho = desfecho

            tarefas_deste = []
            for i, departamento in enumerate(departamentos_escolhidos):
                tarefa_criado_em = comunicado.data_criacao + timedelta(days=random.randint(0, 2))

                if desfecho == "cancelado":
                    status_tarefa = StatusTarefa.CANCELADO
                elif desfecho == "pendente" and i == 0:
                    status_tarefa = StatusTarefa.PENDENTE
                elif desfecho == "rejeitado" and i == len(departamentos_escolhidos) - 1:
                    status_tarefa = StatusTarefa.REJEITADO
                elif desfecho == "aprovado_com_acoes" and i == 0:
                    status_tarefa = StatusTarefa.APROVADO_COM_ACOES
                else:
                    status_tarefa = random.choice([StatusTarefa.APROVADO, StatusTarefa.NAO_SE_APLICA])

                concluida = status_tarefa != StatusTarefa.PENDENTE
                data_conclusao = None
                if concluida and status_tarefa != StatusTarefa.CANCELADO:
                    data_conclusao = min(tarefa_criado_em + timedelta(days=random.randint(1, 20)), hoje)

                tarefa = Tarefa(
                    comunicado=comunicado,
                    departamento=departamento,
                    responsavel=random.choice(responsaveis_por_departamento[departamento.id]),
                    comentarios=self.fake.sentence(nb_words=8),
                    status=status_tarefa,
                    data_conclusao=data_conclusao,
                    justificativa=self.fake.sentence(nb_words=15) if concluida else "",
                )
                tarefa._criado_em_fake = timezone.make_aware(
                    datetime.combine(tarefa_criado_em, time(10, 0))
                )
                tarefas_deste.append(tarefa)
                tarefas.append(tarefa)

            tarefas_por_comunicado[id(comunicado)] = tarefas_deste

        Tarefa.objects.bulk_create(tarefas, batch_size=lote)
        for t in tarefas:
            t.criado_em = t._criado_em_fake
        Tarefa.objects.bulk_update(tarefas, ["criado_em"], batch_size=lote)

        # --- 3) status final do Comunicado, pela mesma regra de negócio real ---
        for comunicado in comunicados:
            if comunicado._desfecho == "cancelado":
                comunicado.status = StatusComunicado.CANCELADO
            else:
                statuses = [
                    t.status for t in tarefas_por_comunicado[id(comunicado)]
                    if t.status != StatusTarefa.CANCELADO
                ]
                comunicado.status = _prioridade_status(statuses)
        Comunicado.objects.bulk_update(comunicados, ["status"], batch_size=lote)

        # --- 4) Ações (só nas Tarefas "Aprovado com ações") --------------------
        self.stdout.write("Gerando Ações...")
        acoes = []
        for tarefa in tarefas:
            if tarefa.status != StatusTarefa.APROVADO_COM_ACOES:
                continue
            responsaveis_dept = responsaveis_por_departamento[tarefa.departamento_id]
            for _ in range(random.randint(1, 2)):
                prazo_dias = random.randint(-30, 60)  # negativo = já vencido
                concluida = random.random() < 0.4
                data_conclusao_acao = None
                status_acao = StatusAcao.PENDENTE
                if concluida:
                    data_conclusao_acao = min(
                        tarefa.data_conclusao + timedelta(days=random.randint(1, 15)), hoje
                    )
                    status_acao = StatusAcao.CONCLUIDO

                acao = Acao(
                    comunicado_id=tarefa.comunicado_id,
                    tarefa=tarefa,
                    departamento_id=tarefa.departamento_id,  # save() normalmente preenche isso, mas bulk_create não chama save()
                    descricao=self.fake.sentence(nb_words=12),
                    status=status_acao,
                    prazo_original=hoje + timedelta(days=prazo_dias),
                    responsavel=random.choice(responsaveis_dept),
                    data_conclusao=data_conclusao_acao,
                )
                acao._data_inclusao_fake = tarefa.data_conclusao
                acoes.append(acao)

        Acao.objects.bulk_create(acoes, batch_size=lote)
        for a in acoes:
            a.data_inclusao = a._data_inclusao_fake
        Acao.objects.bulk_update(acoes, ["data_inclusao"], batch_size=lote)

        return len(comunicados), len(tarefas), len(acoes)
