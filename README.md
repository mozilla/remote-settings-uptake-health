# remote-settings-uptake-worrying

The objective of this script is to check in on the collected uptake from Telemetry
with respect to Remote Settings. Essentially, across all statuses that we worry
about, we use this script to check that the amount of bad statuses don't exceed
a threshold.

The ultimately use case for this script is to run it periodically and use it to
trigger alerts/notifications that the Product Delivery team can take heed of.

## To hack on

```
$ pip install -e ".[dev]"
$ python main.py --help
```
