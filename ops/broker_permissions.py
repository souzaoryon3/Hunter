"""Permissoes de recursos AMQP do Hunter, sem tag administrativa."""

import re


def permissions(prefix="hunter"):
    queues = "^" + re.escape(prefix) + r"\..*"
    # RabbitMQ aplica ACL ao exchange default pelo nome interno amq.default,
    # inclusive ao declarar a DLX de uma fila. O protocolo usa nome vazio.
    return {
        "configure": queues,
        "read": queues,
        "write": r"^(?:" + re.escape(prefix) + r"\..*|amq\.default|)$",
    }
