import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from exception import ResponseError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return bool(PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)


def send_message(bot, message):
    """Отправляем сообщение в Telegram чат."""
    try:
        logger.debug('Начинаем отправку сообщения в чат Telegram')
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение удачно отправлен в чат Telegram')
    except Exception:
        logger.error('Cбой при отправке сообщения в Telegram')
        raise Exception('Cбой при отправке сообщения в Telegram')


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса."""
    try:
        logger.debug('Делаем запрос к эндпоинту API-сервиса.')
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params={'from_date': timestamp},
                                         )
    except Exception as error:
        raise Exception(f'Ошибка при запросе к основному API: {error}')
    if homework_statuses.status_code != HTTPStatus.OK:
        raise Exception('API домашки возвращает код, отличный от 200')
    response = homework_statuses.json()
    if response.get('code') == 'not_authenticated':
        raise ResponseError('Пользователь не авторизован, '
                            'возможно введен неверный токен.')
    logger.info('Ответ получен')
    return response


def check_response(response):
    """Проверяем ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ошибка в типе данных')
    if 'homeworks' not in response:
        raise ResponseError('В ответе нет данных homeworks')
    if 'current_date' not in response:
        raise ResponseError('В ответе нет данных current_date')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Ошибка в типе данных')
    logger.info('Ответ API соответствует документации')
    return homeworks


def parse_status(homework):
    """Извлекаем из информации о конкретной домашней работе статус работы."""
    if 'homework_name' not in homework:
        raise ResponseError('В списке нет данных homework_name')
    if 'status' not in homework:
        raise ResponseError('В списке нет данных status')
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ResponseError('В списке вердиктов отсутствует полученный статус')
    verdict = HOMEWORK_VERDICTS[homework_status]
    logger.info('Есть обновление статуса!')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствуют обязательные переменные окружения!')
        sys.exit('Отсутствуют обязательные переменные окружения!')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_status = ''
    while True:
        try:
            api_answer = get_api_answer(timestamp)
            homeworks = check_response(api_answer)
            timestamp = api_answer.get('current_date')
            logger.info(f'Установлена новая дата: {timestamp}')
            if homeworks:
                message = parse_status(homeworks[0])
                if message != last_status:
                    send_message(bot, message)
                    last_status = message
            else:
                logger.debug('Отсутствие в ответе новых статусов')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
