# Energy Monitor

A simple 6-channel  energy monitor for the whole house.
Uses 0-5V Current Transducers for current measureent and has a build-in voltage transformer for voltage measurement.
Brains are a Raspberry Pi Zero due to low cost and easy integration into the home WiFi and inclusion with MQTT or any other protocol to include the measurements in all kinds of home automation systems.

## Example Configuration

Channels 1, 2, 3 on L1, L2, L3 -> whole house consumption
Channels 4, 5, 6 on different room connections / devices

## Known Limitations

The Voltage is only measured on a single phase and thus only apperant power can be measured on the channels that connect to a different phase than the supply phase
