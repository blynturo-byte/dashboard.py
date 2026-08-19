# API

## Connection

- `is_connected()` - Возвращает `True`, если бот подключен.
- `connect()` - Подключает бота. Возвращает результат подключения.
- `disconnect()` - Отключает бота.
- `reconnect(delay=30.0)` - Переподключает бота через указанную задержку. Запускается в отдельном потоке.
- `SetConnectionProfile(nickname, server=None, server_ip=None, server_port=None, metadata=None)` - Устанавливает ник и адрес сервера. Возвращает `{"nickname": ..., "server": ...}`.
- `getservername()` - Возвращает имя сервера из `server_info`.
- `getserveraddress()` - Возвращает адрес в формате `ip:port`.
- `setserveraddress(ip, port)` - Устанавливает адрес сервера.
- `getbotid()` - Возвращает ID бота.
- `getbotnick()` - Возвращает ник бота.
- `setbotname(nickname)` - Устанавливает ник бота.

## Chat / Dialogs

- `sendchat(message)` - Отправляет сообщение в чат. Строки с `/` отправляются как server command.
- `SendDialogResponse(dialog_id, response, list_item, text="")` - Отправляет ответ на диалог.
- `sendClickTextdraw(textdraw_id)` - Нажимает textdraw.
- `SendKey(keys)` - Устанавливает состояние клавиш бота. Возвращает `True` при успешной установке.

## Pickups / Death

- `SendPickup(pickup_id)` - Отправляет сообщение о подборе pickup.
- `Autopickup(enabled=1)` - Включает или выключает автоматический подбор pickup. Возвращает новое состояние.
- `SendDeathNotification(reason, killer_id=65535)` - Отправляет уведомление о смерти.

## Score / Ping

- `getbotscore()` - Возвращает score бота.
- `getbotping()` - Возвращает ping бота.
- `getplayerscore(player_id)` - Возвращает score игрока.
- `getplayerping(player_id)` - Возвращает ping игрока.
- `sendscoresandpings()` - Запрашивает обновление score и ping.

## Vehicle

- `setbotvehicle(vehicle_id, seat_id=0, switch_state_after=3.0)` - Посаживает бота в транспорт. `vehicle_id=0` выводит бота из транспорта.
- `getbotvehicle()` - Возвращает состояние текущего транспорта бота.
- `setbotvehiclehealth(health)` - Устанавливает здоровье транспорта.

## Players / Stream

- `getallplayers()` - Возвращает всех известных игроков.
- `getallvehicles()` - Возвращает все известные транспортные средства.
- `getvehicle(vehicle_id)` - Возвращает данные транспорта или `None`.
- `getallpickups()` - Возвращает все известные pickup.
- `getpickup(pickup_id)` - Возвращает pickup или `None`.
- `getall3dtextlabels()` - Возвращает все 3D text labels.
- `get3dtextlabel(label_id)` - Возвращает label или `None`.

## Bot state

- `getbothealth()` - Возвращает здоровье бота.
- `setbothealth(health)` - Устанавливает здоровье бота и возвращает новое значение.
- `getbotarmour()` - Возвращает броню бота.
- `setbotarmour(armour)` - Устанавливает броню бота и возвращает новое значение.
- `GetAnimation()` - Возвращает `(animation_id, animation_flags)`.
- `SetAnimation(animation, animation_flags)` - Устанавливает анимацию и её флаги.
- `getbotmoney()` - Возвращает деньги бота.
- `getbotskin()` - Возвращает skin бота.
- `getbotposition()` - Возвращает `(x, y, z)`.
- `setbotposition(x, y, z)` - Телепортирует бота в указанную позицию и отменяет активное движение.
- `getbotrotation()` - Возвращает угол поворота бота.
- `setbotrotation(rotation)` - Устанавливает угол поворота бота.
- `getbotinterior()` - Возвращает interior бота.
- `getbottargetposition()` - Возвращает текущую цель движения.
- `getbotsyncstate()` - Возвращает текущее состояние синхронизации.

## Movement

- `MoveToCoord(x, y, z, ...)` - Запускает движение к координатам. Возвращает `movement_id`.
- `StopMoveToCoord(movement_id=None, reason="cancelled", reset_velocity=True)` - Останавливает активное движение. Возвращает `True`, если движение было остановлено.

Параметры `MoveToCoord` описаны в [`MOVEMENT.md`](MOVEMENT.md).

## Proxy

- `ProxyConnect(proxy_address, timeout=5.0, reconnect=False)` - Подключает proxy.
- `ProxyDisconnect(reconnect=False)` - Отключает proxy.
- `ProxyChange(proxy_address, timeout=5.0, reconnect=True)` - Меняет proxy.
- `ProxyIsConnected()` - Возвращает состояние proxy-соединения.
- `ProxyIsConfigured()` - Возвращает `True`, если proxy настроен.
- `ProxyInfo()` - Возвращает информацию о proxy.
- `ProxyTCPRequest(target_host, target_port, payload, timeout=5.0, recv_size=4096)` - Выполняет TCP-запрос через proxy и возвращает `bytes`.

## Packets

- `SendPacket(payload, reliability=..., ordering_channel=0, priority=...)` - Отправляет произвольный RakNet packet.

## Utility

- `wait(seconds)` - Блокирующий `sleep` на указанное количество секунд.


## Events

События регистрируются через `emitter.on(...)`. Callback получает `bot` первым аргументом. События не возвращают значение.

- `onBotCreated(bot)` - создан объект бота.
- `onRequestConnect(bot)` - запрошено подключение.
- `onOpenConnectionReplyTimeout(bot, attempts, old_ip, old_port)` - истёк таймаут ответа на OpenConnection.
- `onHandshakeFailed(bot, stage, reason, server_ip, server_port)` - handshake завершился ошибкой.
- `onStateReset(bot, reason, counter)` - сброшено runtime-состояние.
- `onconnect(bot)` - подключение завершено и бот перешёл в connected state.
- `disconnect(bot)` - соединение разорвано.
- `onSpawn(bot)` - сервер сообщил о spawn бота.
- `onConnectionRejected(bot, reason_code, reason_text, parsed, packet)` - сервер отклонил подключение.
- `onKick(bot, reason_code, reason_text, parsed, packet)` - получен kick/reject с причиной.
- `onSendPacket(bot, packet_id, body)` - перед отправкой packet.
- `onSendRPC(bot, rpc_id, payload)` - перед отправкой RPC.
- `onReceivePacket(bot, packet_id, payload)` - получен SAMP packet.
- `onReceiveRPC(bot, rpc_id, payload)` - получен RPC.
- `onShowDialog(bot, dialog_id, dialog_style, title, info, button1, button2, parsed, packet)` - сервер показал диалог.
- `OnShowTextDraw(bot, textdraw_id, style, selectable, model_id, parsed, packet)` - сервер показал textdraw.
- `onShowChat(bot, message, parsed, packet)` - получено сообщение чата.
- `onVehicleStreamIn(bot, model_id, vehicle_id, x, y, z)` - транспорт добавлен в stream.
- `onPlayerStreamIn(bot, player_id, skin_id, x, y, z)` - игрок добавлен в stream.
- `onSetMapIcon(bot, icon_id, xyz, marker_type, style, parsed, packet)` - сервер установил map icon.
- `onCreate3DTextLabel(bot, label_id, text, color, x, y, z, draw_distance, use_los, attached_player_id, attached_vehicle_id, parsed, packet)` - создан 3D text label.
- `onPutPlayerInVehicle(bot, vehicle_id, seat_id, parsed, packet)` - бот помещён в транспорт.
- `onPlayerEnterVehicle(bot, player_id, vehicle_id, is_passenger, parsed, packet)` - игрок вошёл в транспорт.
- `OnCoordMoveStart(bot, movement)` - создано движение `MoveToCoord`.
- `OnCoordMovePhaseChange(bot, movement, old_phase, new_phase)` - изменилась фаза движения.
- `OnCoordMoveEnd(bot, movement, status)` - завершилось движение `MoveToCoord`.
- `OnSetPlayerHealth(bot, health)` - сервер установил здоровье боту.
- `OnSetPlayerArmour(bot, armour)` - сервер установил броню боту.
