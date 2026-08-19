
from typing import Callable, Hashable
from concurrent.futures import ThreadPoolExecutor
import threading
from core import logger

class EventEmitter:

    def __init__(self, max_workers: int = 8):
        self._listeners: dict[str, list[Callable]] = {}
        self._keyed_listeners: dict[str, dict[Hashable, list[Callable]]] = {}
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="evt-worker",
        )
        self._shutdown = False
        self._shutdown_lock = threading.Lock()

    def on(self, event: str, key: Hashable = None, sync: bool = False):
        def decorator(func: Callable) -> Callable:
            func._event_sync = sync

            if key is None:
                self._listeners.setdefault(event, []).append(func)
            else:
                self._keyed_listeners.setdefault(event, {}).setdefault(key, []).append(func)

            return func
        return decorator

    def off(self, event: str, func: Callable, key: Hashable = None) -> None:
        if key is None:
            listeners = self._listeners.get(event, [])
            if func in listeners:
                listeners.remove(func)
            return

        listeners = self._keyed_listeners.get(event, {}).get(key, [])
        if func in listeners:
            listeners.remove(func)

    def has_listeners(self, event: str, key: Hashable = None) -> bool:
        if self._listeners.get(event):
            return True

        keyed_map = self._keyed_listeners.get(event)
        if not keyed_map:
            return False

        if key is None:
            return bool(keyed_map)

        return bool(keyed_map.get(key))

    @staticmethod
    def _is_default_handler(func: Callable) -> bool:
        return getattr(func, "__name__", "").startswith("_default_")

    @staticmethod
    def _run_handler(event: str, func: Callable, *args, **kwargs) -> None:
        try:
            func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Events Error in '{event}' handler '{func.__name__}': {e}")

    def _dispatch(self, event: str, func: Callable, args: tuple, kwargs: dict) -> None:
        if self._shutdown:
            return

        if self._is_default_handler(func) or getattr(func, "_event_sync", False):
            self._run_handler(event, func, *args, **kwargs)
            return

        try:
            self._pool.submit(self._run_handler, event, func, *args, **kwargs)
        except RuntimeError as e:
            if self._shutdown or "shutdown" in str(e).lower():
                return

            raise

    def shutdown(self, wait: bool = True) -> None:
        with self._shutdown_lock:
            if self._shutdown:
                return
            self._shutdown = True

        self._pool.shutdown(wait=bool(wait), cancel_futures=True)

    def emit(self, event: str, *args, key: Hashable = None, **kwargs) -> None:
        if self._shutdown:
            return

        generic = self._listeners.get(event)

        specific = None
        if key is not None:
            keyed_map = self._keyed_listeners.get(event)
            if keyed_map:
                specific = keyed_map.get(key)

        if not generic and not specific:
            return

        if generic:
            for func in list(generic):
                self._dispatch(event, func, args, kwargs)

        if specific:
            for func in list(specific):
                self._dispatch(event, func, args, kwargs)


emitter = EventEmitter()



@emitter.on("onBotCreated")
def _default_on_bot_created(bot):
    pass

@emitter.on("onRequestConnect")
def _default_on_request_connect(bot):
    pass

@emitter.on("onOpenConnectionReplyTimeout")
def _default_on_open_connection_reply_timeout(
    bot,
    attempts,
    old_ip,
    old_port,
):
    pass


@emitter.on("onHandshakeFailed")
def _default_on_handshake_failed(
    bot,
    stage,
    reason,
    server_ip,
    server_port,
):
    logger.info(
        f"Handshake failed | stage={stage} | reason={reason} | "
        f"server={server_ip}:{server_port}"
    )

@emitter.on("onStateReset")
def _default_on_state_reset(bot, reason="unknown", counter=0):
    logger.info(f"EVENT State reset: reason={reason}, counter={counter}")

@emitter.on("onconnect")
def _default_on_connect(bot):
    pass
    
@emitter.on("disconnect")
def _default_on_disconnect(bot):
    pass

@emitter.on("onSpawn")
def _default_on_spawn(bot):
    pass

@emitter.on("onConnectionRejected")
def _default_on_connection_rejected(
    bot,
    reason_code,
    reason_text,
    parsed,
    packet,
):
    pass


@emitter.on("onKick")
def _default_on_kick(
    bot,
    reason_code,
    reason_text,
    parsed,
    packet,
):
    pass

@emitter.on("onSendPacket")
def _default_on_send_packet(bot, packet_id, body):
    pass

@emitter.on("onSendRPC")
def _default_on_send_rpc(bot, rpc_id, payload):
    pass

@emitter.on("onReceivePacket")
def _default_on_receive_packet(bot, packet_id, body):
    pass

@emitter.on("onReceiveRPC")
def _default_on_receive_rpc(bot, rpc_id, payload):
    pass

@emitter.on("onShowDialog")
def _default_on_show_dialog(
    bot,
    dialog_id,
    dialog_style,
    title,
    info,
    button1,
    button2,
    parsed,
    packet,
):
    pass


@emitter.on("OnShowTextDraw")
def _default_on_show_text_draw(
    bot,
    textdraw_id,
    style,
    selectable,
    model_id,
    parsed,
    packet,
):
    pass


@emitter.on("onShowChat")
def _default_on_show_chat(
    bot,
    message,
    parsed,
    packet,
):
    pass

@emitter.on("onVehicleStreamIn")
def _default_on_vehicle_stream_in(
    bot,
    model_id,
    vehicle_id,
    x,
    y,
    z,
):
    pass



@emitter.on("onPlayerStreamIn")
def _default_on_player_stream_in(
    bot,
    player_id,
    skin_id,
    x,
    y,
    z,
):
    pass



@emitter.on("onSetMapIcon")
def _default_on_set_map_icon(
    bot,
    icon_id,
    xyz,
    marker_type,
    style,
    parsed,
    packet,
):
    pass


@emitter.on("onCreate3DTextLabel")
def _default_on_create_3d_text_label(
    bot,
    label_id,
    text,
    color,
    XLabel,
    YLabel,
    ZLabel,
    draw_distance,
    use_los,
    attached_player_id,
    attached_vehicle_id,
    parsed,
    packet,
):
    pass


@emitter.on("onPutPlayerInVehicle")
def _default_on_put_player_in_vehicle(
    bot,
    vehicle_id,
    seat_id,
    parsed,
    packet,
):
    pass



@emitter.on("onPlayerEnterVehicle")
def _default_on_player_enter_vehicle(
    bot,
    player_id,
    vehicle_id,
    is_passenger,
    parsed,
    packet,
):
    pass

@emitter.on("OnCoordMoveStart")
def _default_on_coord_move_start(bot, movement):
    pass


@emitter.on("OnCoordMovePhaseChange")
def _default_on_coord_move_phase_change(
    bot,
    movement,
    old_phase,
    new_phase,
):
    pass


@emitter.on("OnCoordMoveEnd")
def _default_on_coord_move_end(bot, movement, status):
    pass


@emitter.on("OnSetPlayerHealth")
def _default_on_set_player_health(bot, health):
    pass


@emitter.on("OnSetPlayerArmour")
def _default_on_set_player_armour(bot, armour):
    pass
