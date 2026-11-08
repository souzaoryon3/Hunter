"""Logs operacionais sem URLs de conexão ou mensagens de exceção externas."""
import logging


def configure_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)sZ %(levelname)s %(message)s')
    import time
    logging.Formatter.converter = time.gmtime
    # Bibliotecas AMQP podem registrar a URL na reconexão. O runtime registra
    # somente a classe do erro nos seus próprios pontos de recuperação.
    for name in ('aio_pika', 'aiormq'):
        logging.getLogger(name).setLevel(logging.CRITICAL + 1)
    for name, logger in logging.Logger.manager.loggerDict.items():
        if name.startswith(('aio_pika.', 'aiormq.')) and isinstance(logger, logging.Logger):
            logger.setLevel(logging.CRITICAL + 1)
