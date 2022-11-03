# tensormeterclient
python client for the Tensormeter RTM server.

This is a multithreaded client to the Tensormeter RTM1 server. Client gets notified on messages from the RTM server and updates its stored parameter and data values accordingly.

This project is work-in-progress!

## Authors
Michael Schneider, MBI Berlin

## Example usage

Connect to device control server, clear data buffer, then measure and retrieve a defined number of values
```python
tm =  TensormeterRTM1Client('192.168.0.16', 6340)
tm.clear_data()
tm.measure(100)
# check how many values are left to measure
tm.meas  # number decreases until it reaches zero
...
data = tm.get_data()
```

Current parameter values can directly be accessed via their command names (as defined in the Tensormeter manual). Examples:

```python
tm.lfrq  # lock-in frequency
tm.avgt  # averaging time
tm.vamp  # voltage amplitude
...
```

By default, the Tensormeter RTM server sends messages with all parameter values when a client connects. Additional messages are sent automatically when a parameter value changes (either from the server gui or from a client) to inform the client of new values.
