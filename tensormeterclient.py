import threading
import selectors
import time
import socket
import struct
import logging
import numpy as np



class TensormeterData:
    """Holds a dictionary ("data") of all available Tensormeter data.
    Provides pack and unpack methods to convert between python types and
    binary data expected by Tensormeter RTM Server.
    """

    LUT = {
        # param: (dimensions, format)
        "avgt": (0, 'd'),
        "lfrq": (0, 'd'),
        "vamp": (0, 'd'),
        "vpro": (0, 'd'),
        "camp": (0, 'd'),
        "cpro": (0, 'd'),
        "virg": (0, 'd'),
        "cudc": (0, 'd'),
        "vodc": (0, 'd'),
        "vorg": (0, 'd'),
        "crng": (0, 'd'),
        "sres": (0, 'd'),
        "aaup": (0, '?'),
        "tcai": (0, '?'),
        "refe": (0, '?'),
        "cmod": (0, 'H'),
        "amod": (0, 'H'),
        "mod?": (0, 'H'),
        "trmo": (0, 'I'),
        "meas": (0, 'i'),
        "swit": (1, 'I'),
        "selc": (1, 'i'),
        "puar": (1, 'd'),
        "newd": (2, 'd'),
        "alld": (2, 'd'),
        "mult": (0, 'H'),
        "auup": (0, '?'),
    }

    def __init__(self):
        self.data = {k: None for k in self.LUT}
        self.data["TENS"] = ''

    def pack(self, cmd: str, data) -> bytes:
        dims, fmt = self.LUT[cmd]
        if dims == 0:
            return struct.pack('>' + fmt, data)
        elif dims == 1:
            count = len(data)
            return struct.pack(f">I {count}{fmt}", count, *data)
        else:
            # never need to send more than 1d
            raise NotImplementedError

    def unpack(self, cmd: str, data: bytes):
        if cmd == "TENS":
            return cmd + data.decode("ASCII")

        dims, fmt = self.LUT[cmd]
        if dims == 0:
            return struct.unpack('>' + fmt, data)[0]
        elif dims == 1:
            count, = struct.unpack('>I', data[:4])
            return struct.unpack(f">{count}{fmt}", data[4:])
        elif dims == 2:
            rows, cols = struct.unpack('>2I', data[:8])
            array = np.frombuffer(data, np.dtype('>' + fmt), offset=8)
            return array.reshape(cols, rows)
        else:
            raise NotImplementedError

    def update(self, cmd: str, data: bytes):
        if cmd not in self.data:
            raise ValueError(f"Unknown data field: {cmd}, {len(data)} bytes")
        else:
            self.data[cmd] = self.unpack(cmd, data)


class TensormeterRTM1Client:

    def __init__(self, host, port, dataformat="binary"):
        if dataformat != "binary":
            raise NotImplementedError("ASCII format not yet implemented")
        self._tensordata = TensormeterData()
        self._log = logging.getLogger("tensormeter")
        self._log.setLevel(logging.DEBUG)
        self._sel = selectors.DefaultSelector()
        self.host = host
        self.port = port
        self._log.info(f"Connecting to RTM Server at {host}:{port}")
        self.connect()
        self.send("*IDN?")
        # self._log.info(f"Connected to {self.IDN}")

    def connect(self):
        self._s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._s.connect((self.host, self.port))
        self._s.setblocking(False)
        self._selreg = self._sel.register(self._s, selectors.EVENT_READ)
        self._stopped = False
        self._start_listening_thread()

    def _start_listening_thread(self):
        self._data_ready_event = threading.Event()
        thread = threading.Thread(target=self._reader, args=())
        thread.daemon = True
        thread.start()

    def _reader(self):
        while not self._stopped:
            events = self._sel.select(timeout=None)
            for event in events:
                msglen = self._s.recv(4)
                if msglen:
                    length = struct.unpack('>I', msglen)[0] - 4
                    cmd = self._s.recv(4).decode("ASCII")
                    data = self._s.recv(length)
                    while len(data) != length:
                        self._sel.select()
                        data += self._s.recv(length - len(data))
                    self._log.debug(f"Received {cmd}, {length} data bytes")

                    if data:
                        try:
                            self._tensordata.update(cmd, data)
                        except ValueError as exc:
                            self._log.error(f"Error updating field {cmd}: {exc}")
                    if cmd in ["newd", "alld"]:
                        self._data_ready_event.set()
                else:
                    # connection closed on remote end
                    self._log.error("Remote server shut down. Closing socket.")
                    self._stopped = True
                    self.close()

    def send(self, cmd: str, data=None):
        data_bytes = self._tensordata.pack(cmd, data) if data else b''
        cmd_bytes = cmd.encode("ASCII")
        count = len(cmd_bytes) + len(data_bytes)
        msg = struct.pack(f'>I {len(cmd)}s', count, cmd_bytes) + data_bytes
        hexstr = ' '.join(f"{c:02X}" for c in msg)
        self._log.debug(f"Send {cmd}: {hexstr}")
        self._s.send(msg)

    def close(self):
        self._sel.unregister(self._selreg.fd)
        self._sel.close()
        self._s.close()

    @property
    def IDN(self):
        return self._tensordata.data["TENS"]

    def __getattr__(self, cmd):
        if cmd in self._tensordata.data:
            return self._tensordata.data[cmd]
        else:
            raise AttributeError

    def measure(self, nmeas: int):
        self.send("meas", nmeas)

    def select_channels(self, channels: list[int]):
        self.send("selc", channels)

    def clear_data(self):
        self.send("cldt")

    def get_data(self, timeout=0.5, all_data=False):
        cmd = "alld" if all_data else "newd"
        self.send(cmd)
        if self._data_ready_event.wait(timeout):
            self._data_ready_event.clear()
            return self._tensordata.data[cmd]
        else:
            raise TimeoutError("Timeout while waiting for data")

