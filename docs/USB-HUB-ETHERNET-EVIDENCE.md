# Evidence: USB Hub Ethernet Port on Benro Polaris

## Observation (2026-09-15)

When a powered USB hub with an integrated Realtek RTL8153 Gigabit Ethernet adapter is connected to the Benro Polaris gimbal:

- The device is detected as `Bus 001 Device 007: ID 0bda:8152` (Realtek RTL8153).
- The corresponding network interface appears as `eth0`.
- The `r8152` kernel driver is in use (visible in `dmesg` and `/sys/class/net/eth0/device/driver`).
- Initially, the interface is down:
  ```
  3: eth0: <BROADCAST,MULTICAST> mtu 1500 qdisc noop qlen 1000
      link/ether 00:e0:4c:36:01:61 brd ff:ff:ff:ff:ff:ff
  ```
  (Note: `qdisc noop` and absence of `UP` flag indicate the link is not active.)

## Implications for Plugging in an Ethernet Cable

- **Link Layer**: Plugging an Ethernet cable into the hub's Ethernet port should cause the link to come up automatically (assuming the cable and far-end device are functional). The `r8152` driver supports auto-negotiation and will report `carrier` and update the interface flags to include `UP` and `LOWER_UP`.
- **IP Configuration**: The Polaris does **not** run a DHCP client on `eth0` by default. The system runs a `udhcpd` daemon (likely for serving DHCP to clients when the Polaris acts as a Wi‑Fi AP), but there is no `udhcpc` or similar client configured for `eth0`.
  - Therefore, simply plugging in the cable will **not** automatically obtain an IP address via DHCP.
  - To use the Ethernet connection, one would need to:
    1. Ensure the link is up (plug cable, verify with `ip link show eth0`).
    2. Start a DHCP client (e.g., `udhcpc -i eth0`) or configure a static IP address.
- **Persistence**: Any configuration changes (starting a DHCP client, setting a static IP) would be temporary unless saved to a startup script or network configuration file.

## Future Use

This evidence indicates that the USB hub's Ethernet port is a viable path for wired network connectivity on the Polaris, provided that:
- The `r8152` driver is present and functional (it is).
- A DHCP client or static IP configuration is applied after the link is up.

For automated use, one could consider adding a script to `/etc/init.d/` or similar to launch `udhcpc` on `eth0` when the interface is detected, but that would constitute a configuration change on the device.

## Related Files on the Polaris

- `/app/wifi/udhcpd.conf` – configuration for the existing DHCP server (Wi‑Fi AP).
- `/etc/udev/rules.d/11-usb-hotplug.rules` – triggers scripts on USB device events (could be leveraged to start a DHCP client).
- `/etc/udev/usbdev-hotplug.sh` – the hotplug script invoked by the above rule.

## Conclusion

Plugging a wireless network cable (interpreted as an Ethernet cable) into the hub's Ethernet port **will not just work** for IP connectivity without additional configuration. The link layer will come up, but IP address acquisition requires running a DHCP client or setting a static IP.