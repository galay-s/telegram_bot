# -*- coding: utf-8 -*-
import requests
import time
import gevent
from gevent.event import AsyncResult
from gevent import monkey
monkey.patch_all()

TELEGRAM_TOKEN = ''
API_URL = 'https://api.telegram.org/bot'

BETHUNTER_URL = 'http://bethunter24.com/api/bot/find/games'
BETHUNTER_TOKEN = '123'


class Bethunter24(object):
    """Класс работающий с сервисом который отдает по API
    информацию со ставками в спорте.
    """

    def __init__(self, token):
        self._token = token
        self._client = requests.Session()

    def get_game_info(self, *args, **kwargs):
        """ Получаем инфо игр"""

        if len(args) < 2:
            result[kwargs['index']].set(
                {"error": "Use format: next_period prev_period text_query."}
            )
        elif args[0].isdigit() and args[1].isdigit():
            data = {"token": self._token,
                    "filter": {"next_period": int(args[0]),
                               "prev_period": int(args[1]),
                               "text_query": args[2] if len(args) > 2 else ''},
                    "select": {"odds": True}}

            response = self._client.post(BETHUNTER_URL, json=data)

            if response.status_code == 200:
                result[kwargs['index']].set(response.json())
            else:
                result[kwargs['index']].set(
                    {"error": "No response from Bethunter24"}
                )


class TelegramBot(object):

    def __init__(self, token):
        """Если скрипт был остановлен, то считываем из файла последний update.
        Если этого не сделать, то повторно будут обработаны все сообщения
        полученные от пользователей.
        """

        with open('last_update_id.txt', 'r') as f:
            last_update_id = f.read()
            self.last_update_id = int(last_update_id) if last_update_id else 0
        self._token = token
        self._client = requests.Session()

    def get_update(self):
        """Получаем обновления от Telegrmam.
        В них находится информация такая как id обновления,
        id чата, текст сообщения, кто написал сообщения.
        """

        return self._client.get(
            '{}{}/getUpdates'.format(API_URL, self._token)
        ).json()

    def send_message(self, chat_id, text):
        """Отправка сообщения в чат"""

        data = {'text': text,
                'chat_id': chat_id,
                'parse_mode': 'HTML'}

        return self._client.post(
            '{}{}/sendMessage'.format(API_URL, self._token),
            data=data
        )

    def _is_new(self, update_id):
        """Проверяет новое ли это обновление.
        Скрипт постоянно хранит id последнего обновления (last_update_id). Если
        приходит обновления большее чем last_update_id, то это признак нового.
        """

        return update_id > self.last_update_id

    def _save_last_update_id(self, list_update_ids):
        """Сохраняет id последнего обновления
        Так же сохраняет в файл на тот случай если скрипт будет остановлен.
        При повторном запуске эти данные считываются в __init__
        """

        self.last_update_id = max(list_update_ids)
        with open('last_update_id.txt', 'w') as f:
            f.write(str(self.last_update_id))

    def _parse_text(self, text):
        """Парсит строку посланную пользователем
        и возвращает список с фильтрами
        Фильтры от пользователя разделяются пробелами
        """

        return text.split(' ')

    def _get_bookmaker_url(self, game):
        """Возвращает URL букмеккерской конторы"""

        if game.get('odds'):
            return '<i>{}</i>'.format(game.get('odds')[0].get('source_url'))

        return '<i>No URL</i>'

    def _create_message_and_send(self, chat_id, **kwargs):
        """Формирует сообщение в читаемом виде и отсылает пользователю"""

        data = result[kwargs['index']].get()
        if data.get('error'):
            self.send_message(chat_id, data.get('error'))
        elif not data.get('games'):
            self.send_message(chat_id, 'Not found')
        else:
            for game in data.get('games'):
                message = '\n'.join([
                    game.get('data_text'),
                    game.get('starts_at'),
                    self._get_bookmaker_url(game)
                ])
                for odd in game.get('odds'):
                    message += "\n{0} ({1}) :: {2}".format(
                        odd.get('event'),
                        odd.get('allowance'),
                        odd.get('value')
                    )
                message += "\n"

                self.send_message(chat_id, message)

    def check_new_messages(self, get_game_info, update):
        """Проходит циклом по всем сообщениям полученным из update.
        Если есть новые сообщения, то парсим сообщения, делаем запрос к
        http://bethunter24.com/api/bot/find/games и возвращаем результат.
        Telegram принимает не больше 4096 символов в сообщении, по этому
        разбиваем его на несколько.
        """

        new_update_ids = []
        for index, message in enumerate(update.get('result')):
            result.append(AsyncResult())
            if self._is_new(message.get('update_id', 0)):
                new_update_ids.append(message.get('update_id', 0))
                filters = self._parse_text(
                    message.get('message', {'text': ''}).get('text')
                )

                print(message.get('message', {'text': ''}).get('text'))

                jobs.append(gevent.spawn(get_game_info,
                                         *filters,
                                         index=index
                                         ))

                jobs.append(gevent.spawn(
                    self._create_message_and_send,
                    message.get(
                        'message',
                        {'chat': {'id': 0}}
                    ).get('chat', {'id': 0}).get('id'),
                    index=index)
                )

        if new_update_ids:
            self._save_last_update_id(new_update_ids)


if __name__ == '__main__':
    bot = TelegramBot(TELEGRAM_TOKEN)
    bethunter = Bethunter24(BETHUNTER_TOKEN)

    while True:
        result = []  # для передачи информации между гринлетами (AsyncResult)
        jobs = []  # список для гринлетов
        update = bot.get_update()
        bot.check_new_messages(bethunter.get_game_info, update)
        gevent.joinall(jobs)
        time.sleep(1)
