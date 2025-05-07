import logging


def get_logger() -> logging.Logger:

    # Cria o logger principal
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Handler para arquivo
    file_handler = logging.FileHandler('apontamento.log', mode='a', encoding = 'utf-8')
    file_handler.setFormatter(formatter)

    # Handler para console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
