from typing import Optional, Tuple

from bleak import BleakClient, BleakScanner

__all__ = ["Coyote2"]
__version__ = "0.1.0-dev"

BLE_DEVICE_NAME = "D-LAB ESTIM01"

SERVICE_A_UUID = "955A180A-0FE2-F5AA-A094-84B8D4F3E8AD"

BATTERY_LEVEL_UUID = "955A1500-0FE2-F5AA-A094-84B8D4F3E8AD"
PWM_AB2_UUID = "955A1504-0FE2-F5AA-A094-84B8D4F3E8AD"
PWM_A34_UUID = "955A1505-0FE2-F5AA-A094-84B8D4F3E8AD"
PWM_B34_UUID = "955A1506-0FE2-F5AA-A094-84B8D4F3E8AD"


class Coyote2Error(RuntimeError):
    pass


class AlreadyConnectedError(Coyote2Error):
    pass


class NotConnectedError(Coyote2Error):
    pass


class DeviceIsNotCoyote20Error(Coyote2Error):
    pass


class DeviceNotFoundError(Coyote2Error):
    pass


class Coyote2:
    def __init__(self, address: Optional[str] = None):
        self.address = address
        self.__client = None

    async def find_device(self) -> bool:
        device = await BleakScanner.find_device_by_name(BLE_DEVICE_NAME)
        if not device:
            return False
        self.address = device.address
        return True

    @property
    def client(self):
        if self.__client is None:
            self.__client = BleakClient(
                self.address, winrt={"use_cached_services": False}
            )
        return self.__client

    @property
    def is_connected(self):
        return self.client.is_connected

    async def connect(self):
        assert self.address is not None
        if self.is_connected:
            raise AlreadyConnectedError
        await self.client.connect()
        for service in self.client.services:
            if service.uuid == SERVICE_A_UUID.lower():
                break
        else:
            await self.disconnect()
            raise DeviceIsNotCoyote20Error

    async def disconnect(self):
        await self.client.disconnect()

    async def __aenter__(self):
        if self.address is None:
            found_device = self.find_device()
            if not found_device:
                raise DeviceNotFoundError
        await self.connect()

    async def __aexit__(self, type, value, trace):
        await self.disconnect()

    def __check_connection(self):
        if not self.is_connected:
            raise NotConnectedError

    async def get_battery_level(self) -> int:
        self.__check_connection()
        data = await self.client.read_gatt_char(BATTERY_LEVEL_UUID)
        battery_level = data[0]
        return battery_level

    async def _get_real_strength(self) -> Tuple[int, int]:
        self.__check_connection()
        data = await self.client.read_gatt_char(PWM_AB2_UUID)
        data_int = int.from_bytes(data, "little", signed=False)
        real_strength_a = data_int >> 13
        real_strength_b_mask = 0b0000000000011111111111
        real_strength_b = (data_int >> 2) & real_strength_b_mask
        return real_strength_a, real_strength_b

    async def get_strength(self) -> Tuple[float, float]:
        real_strength_a, real_strength_b = await self._get_real_strength()
        return real_strength_a / 7, real_strength_b / 7

    async def _write_real_strength(self, real_strength_a: int, real_strength_b: int):
        assert 0 <= real_strength_a <= 2047 and 0 <= real_strength_b <= 2047, "Not a vaild strength"
        self.__check_connection()
        data_int = 0
        data_int += real_strength_a
        data_int <<= 11
        data_int += real_strength_b
        data_int <<= 2
        data = data_int.to_bytes(3, "little", signed=False)
        await self.client.write_gatt_char(PWM_AB2_UUID, data)

    async def write_strength(self, strength_a: float, strength_b: float):
        await self._write_real_strength(int(strength_a * 7), int(strength_b * 7))

    async def __read_wave(self, uuid: str):
        self.__check_connection()
        data = await self.client.read_gatt_char(uuid)
        data_int = int.from_bytes(data, "little", signed=False)
        x = data_int >> 19
        y_mask = 0b000001111111111
        y = (data_int >> 9) & y_mask
        z_mask = 0b00000000000000011111
        z = (data_int >> 2) & z_mask
        return x, y, z

    async def __write_wave(self, uuid: str, x: int, y: int, z: int):
        assert 0 <= x <= 31 and 0 <= y <= 1023 and 0 <= z <= 31, "Not a vaild wave"
        if not self.is_connected:
            raise NotConnectedError
        data_int = 0
        data_int += x
        data_int <<= 10
        data_int += y
        data_int <<= 5
        data_int += z
        data_int <<= 2
        data = data_int.to_bytes(3, "little", signed=False)
        await self.client.write_gatt_char(uuid, data)

    async def read_wave_a(self) -> Tuple[int, int, int]:
        return await self.__read_wave(PWM_B34_UUID)

    async def write_wave_a(self, x: int, y: int, z: int):
        await self.__write_wave(PWM_B34_UUID, x, y, z)

    async def read_wave_b(self) -> Tuple[int, int, int]:
        return await self.__read_wave(PWM_A34_UUID)

    async def write_wave_b(self, x: int, y: int, z: int):
        await self.__write_wave(PWM_A34_UUID, x, y, z)
