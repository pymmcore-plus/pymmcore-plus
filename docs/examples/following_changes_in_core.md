# Follow changes in MMCore

`pymmcore-plus` implements an enhanced [Observer pattern](https://en.wikipedia.org/wiki/Observer_pattern), making it easier to connect callback functions to events that occur
in the core.  This is useful for things like updating a GUI when a property changes,
or writing and/or processing data as it is acquired.

See the [Events API documentation](../../api/events) for complete details on what events are emitted
and how to connect to them.

```python linenums="1" title="on_prop_changed.py"
--8<-- "examples/properties_and_state_events.py"
```
