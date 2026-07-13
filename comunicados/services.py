from django.db import transaction
from django.utils import timezone

from tarefas.models import StatusTarefa, Tarefa

from .models import ContadorCaiFiscal, StatusComunicado


def calcular_ano_fiscal(data):
    """Ano fiscal thyssenkrupp: outubro a setembro, rótulo tipo "25'26".

    Outubro a dezembro pertencem ao ano fiscal que começa nesse ano civil;
    janeiro a setembro pertencem ao ano fiscal que começou no ano civil anterior.
    """
    ano = data.year
    if data.month > 9:
        inicio, fim = ano, ano + 1
    else:
        inicio, fim = ano - 1, ano
    return f"{inicio % 100:02d}'{fim % 100:02d}"


def criar_comunicado(dados_comunicado, tarefas_data, anexos=None):
    """Cria o Comunicado com seu CaiFiscal (ano_fiscal + numero_sequencial), as
    Tarefas iniciais e os anexos, tudo em uma única transação.

    dados_comunicado: campos de Comunicado, exceto ano_fiscal/numero_sequencial/
                      cai_fiscal (gerados aqui) — data_criacao é opcional (default
                      hoje). Se "cancela_comunicado" vier preenchido, esse outro
                      Comunicado é marcado como Cancelado.
    tarefas_data: lista de dicts com os campos de cada Tarefa (departamento obrigatório).
    anexos: lista de UploadedFile (request.FILES), opcional.
    """
    from .models import Comunicado, ComunicadoAnexo

    data_criacao = dados_comunicado.get("data_criacao") or timezone.localdate()
    ano_fiscal = calcular_ano_fiscal(data_criacao)

    with transaction.atomic():
        contador, _ = ContadorCaiFiscal.objects.get_or_create(ano_fiscal=ano_fiscal)
        contador = ContadorCaiFiscal.objects.select_for_update().get(pk=contador.pk)
        contador.ultimo_numero += 1
        contador.save(update_fields=["ultimo_numero"])
        numero_sequencial = contador.ultimo_numero

        comunicado = Comunicado.objects.create(
            **{**dados_comunicado, "data_criacao": data_criacao},
            ano_fiscal=ano_fiscal,
            numero_sequencial=numero_sequencial,
            cai_fiscal=f"{numero_sequencial} / {ano_fiscal}",
        )

        for dados_tarefa in tarefas_data:
            Tarefa.objects.create(comunicado=comunicado, **dados_tarefa)

        for arquivo in anexos or []:
            ComunicadoAnexo.objects.create(
                comunicado=comunicado, arquivo=arquivo, nome_original=arquivo.name
            )

        cai_cancelado = dados_comunicado.get("cancela_comunicado")
        if cai_cancelado:
            Comunicado.objects.filter(pk=cai_cancelado.pk).update(
                status=StatusComunicado.CANCELADO
            )

    return comunicado


def _prioridade_status(statuses):
    """Núcleo puro da regra de prioridade (ver docstring de calcular_status).
    Recebe a lista de status de Tarefa já sem as Canceladas. Extraído à parte
    para o gerador de dados fictícios (management command) poder aplicar a
    MESMA regra de negócio sobre listas em memória, sem bater no banco —
    evita que o script de seed divirja da regra real."""
    if not statuses:
        return StatusComunicado.PENDENTE

    if StatusTarefa.REJEITADO in statuses:
        return StatusComunicado.REJEITADO

    if StatusTarefa.PENDENTE in statuses:
        return StatusComunicado.PENDENTE

    if StatusTarefa.APROVADO_COM_ACOES in statuses:
        return StatusComunicado.APROVADO_COM_ACOES

    return StatusComunicado.APROVADO


def calcular_status(comunicado):
    """Deriva o status do Comunicado a partir do status de suas Tarefas.

    Ordem de prioridade (não alterar sem revisar as regras de negócio):
    1. Qualquer Tarefa Rejeitada          -> Rejeitado, IMEDIATO (não espera
       as demais Tarefas responderem — é o único caso que ignora pendências)
    2. Ainda existe Tarefa Pendente       -> Pendente (as outras 3 regras só
       se aplicam quando não sobra nenhuma Tarefa pendente — confirmado pelo
       fluxo real do Power Apps, que só calcula o status final do CAI depois
       de checar CountRows(Filter(Tarefas; Status = Pendente)) = 0)
    3. Qualquer Tarefa Aprovado c/ações   -> Aprovado com ações
    4. Caso contrário (só Aprovado/Não se aplica) -> Aprovado

    Tarefas Canceladas são ignoradas na avaliação, assim como as Ações
    (que nunca influenciam o status do Comunicado).
    """
    statuses = list(
        comunicado.tarefas.exclude(status=StatusTarefa.CANCELADO).values_list(
            "status", flat=True
        )
    )
    return _prioridade_status(statuses)


def atualizar_status_comunicado(comunicado):
    """Recalcula e persiste o status do Comunicado, se ele tiver mudado.

    Retorna True quando o status foi alterado (útil para os signals decidirem
    se devem disparar o e-mail de "Comunicado finalizado").
    """
    novo_status = calcular_status(comunicado)
    if novo_status == comunicado.status:
        return False

    comunicado.status = novo_status
    comunicado.save(update_fields=["status", "atualizado_em"])
    return True


def cancelar_comunicado(comunicado):
    """Cancelamento manual (botão na lista de Comunicados). Cascata igual à
    rejeição: Tarefas e Ações ainda pendentes também são canceladas, já que o
    CAI inteiro está sendo abandonado."""
    from acoes.services import cancelar_acoes_pendentes_do_comunicado

    with transaction.atomic():
        comunicado.tarefas.filter(status=StatusTarefa.PENDENTE).update(
            status=StatusTarefa.CANCELADO
        )
        cancelar_acoes_pendentes_do_comunicado(comunicado)
        comunicado.status = StatusComunicado.CANCELADO
        comunicado.save(update_fields=["status", "atualizado_em"])

    return comunicado
