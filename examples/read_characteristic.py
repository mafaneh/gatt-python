import sys
import dbus
import gatt
from gatt import errors

from argparse import ArgumentParser

global g_mac_address
global g_service
global g_characteristic
global g_manager
global g_device

class InvalidArgs(Exception):
    pass

def _error_from_dbus_error(e):
    return {
        'org.bluez.Error.Failed': errors.Failed(e.get_dbus_message()),
        'org.bluez.Error.InProgress': errors.InProgress(e.get_dbus_message()),
        'org.bluez.Error.InvalidArgs': InvalidArgs(e.get_dbus_message()),
        'org.bluez.Error.InvalidValueLength': errors.InvalidValueLength(e.get_dbus_message()),
        'org.bluez.Error.NotAuthorized': errors.NotAuthorized(e.get_dbus_message()),
        'org.bluez.Error.NotPermitted': errors.NotPermitted(e.get_dbus_message()),
        'org.bluez.Error.NotSupported': errors.NotSupported(e.get_dbus_message()),
        'org.freedesktop.DBus.Error.AccessDenied': errors.AccessDenied("Root permissions required")
    }.get(e.get_dbus_name(), errors.Failed(e.get_dbus_message()))

class AnyDevice(gatt.Device):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._battery_properties_signal = None

    def connect_failed(self, error):
        global g_mac_address
        global g_manager

        print("Connection to", g_mac_address, "failed, error:", error)
        #super().connect_failed(error)
        g_manager.stop()

    def connect_succeeded(self):
        global g_mac_address

        print("Connection to", g_mac_address, "succeeded, waiting for services to be resolved...")

        super().connect_succeeded()

    def disconnect_succeeded(self):
        global g_mac_address
        global g_manager

        print("Disconnection from", g_mac_address, "succeeded.")

        self._battery_disconnect_signals()
        super().disconnect_succeeded()
        g_manager.stop()

    def _battery_connect_signals(self):
        if self._battery_properties_signal is None:
            self._battery_properties_signal = self._battery_properties.connect_to_signal('PropertiesChanged', self.battery_properties_changed)

    def _battery_disconnect_signals(self):
        if self._battery_properties_signal is not None:
            self._battery_properties_signal.remove()
            self._battery_properties_signal = None

    def battery_properties_changed(self, properties, changed_properties, invalidated_properties):
        """
        Called when a battery property has changed.
        """
        percentage = changed_properties.get('Percentage')
        if percentage is not None:
            print("Battery level is now at", int(percentage), "percent.")

    def services_resolved(self):
        global g_mac_address
        global g_service
        global g_characteristic
        global g_device

        super().services_resolved()

        self._battery_object = dbus.Interface(self.device_object, 'org.bluez.Battery1')
        self._battery_properties = dbus.Interface(self._battery_object, 'org.freedesktop.DBus.Properties')
        self._battery_connect_signals()
        try:
            percentage = self._battery_properties.Get('org.bluez.Battery1', 'Percentage')
            print("Battery level is initially at", int(percentage), "percent.")
        except dbus.exceptions.DBusException as e:
            error = _error_from_dbus_error(e)
            print("Battery level cannot be read, error:", error)

        try:
            selected_service = next(
                s for s in self.services
                if s.uuid == '0000' + g_service + '-0000-1000-8000-00805f9b34fb')

            selected_characteristic = next(
                c for c in selected_service.characteristics
                if c.uuid == '0000' + g_characteristic + '-0000-1000-8000-00805f9b34fb')

            print("Service", g_service, "Characteristic", g_characteristic, "exists, reading value...")
            selected_characteristic.read_value()
        except StopIteration:
            print("Service", g_service, "Characteristic", g_characteristic, "does not exist!")
            print("Disconnecting from", g_mac_address, "...")
            g_device.disconnect()

    def characteristic_read_value_failed(self, characteristic, error):
        global g_mac_address
        global g_service
        global g_characteristic
        global g_device

        super().characteristic_read_value_failed(characteristic, error)

        print("Service", g_service, "Characteristic", g_characteristic, "read_value failed, error:", error)
        print("Disconnecting from", g_mac_address, "...")
        g_device.disconnect()

    def characteristic_value_updated(self, characteristic, value):
        global g_mac_address
        global g_service
        global g_characteristic
        global g_device

        super().characteristic_value_updated(characteristic, value)

        print("Service", g_service, "Characteristic", g_characteristic, "value:", value.decode("utf-8"))
        print("Disconnecting from", g_mac_address, "...")
        g_device.disconnect()


arg_parser = ArgumentParser(description="GATT Read Characteristic Demo")
arg_parser.add_argument('mac_address', help="MAC address of device to connect")
arg_parser.add_argument('service', help="16-bit service ID (e. g., 180a)")
arg_parser.add_argument('characteristic', help="16-bit characteristic ID (e. g., 2a26)")
args = arg_parser.parse_args()

g_mac_address = args.mac_address.upper()
g_service = args.service.lower()
g_characteristic = args.characteristic.lower()

g_manager = gatt.DeviceManager(adapter_name='hci0')
g_device = AnyDevice(manager=g_manager, mac_address=g_mac_address)

print("Connecting to", g_mac_address, "...")
g_device.connect()

g_manager.run()
