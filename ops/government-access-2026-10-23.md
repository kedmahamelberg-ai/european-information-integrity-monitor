# Government source access comparison — 23 October 2026

The 17 exact official news URLs previously checked were requested again through a connected Cloudflare WARP client whose exit was in the Netherlands. Separate [Globalping HTTP GET probes](https://github.com/jsdelivr/globalping/blob/master/public/v1/spec.yaml) requested each URL from up to two IPs geolocated in its own country. `200` means the section responded; it does not verify that its archive or articles can be parsed. `403` means that request was refused, not that the site was offline. A timeout also does not establish an outage.

| Country | WARP NL | Country-local probes | Measurement |
| --- | --- | --- | --- |
| Albania | 403 | 403, 403 (Cloudflare challenges) | [AL](https://api.globalping.io/v1/measurements/2UgHkY4kQVtINzBoH00021MuA) |
| Azerbaijan | Timeout | Timeout, 200 | [AZ](https://api.globalping.io/v1/measurements/2dSZRL8ONDBFTynzv00021MuC) |
| Cyprus | 403 | 403, 403 | [CY](https://api.globalping.io/v1/measurements/2GYaRCPxIymvUc3K600021MuA) |
| Finland | 403 | 200, 200 | [FI](https://api.globalping.io/v1/measurements/2fUHKXExJmKV7GB9900021MuA) |
| France | 403 | 403, 403 (Cloudflare challenges) | [FR](https://api.globalping.io/v1/measurements/24DoUdrWMfrlAHNQY00021MuA) |
| Ireland | 403 | 403, 403 | [IE](https://api.globalping.io/v1/measurements/2012PePl9c072oKS400021MuA) |
| Latvia | Timeout | 200, 200 | [LV](https://api.globalping.io/v1/measurements/2bhKrGyzN5zcRLU6E00021MuA) |
| Lithuania | 403 | 200, 200 | [LT](https://api.globalping.io/v1/measurements/2njAQ7i3cj6YzkeLI00021MuA) |
| Malta | 200 | 403, 403 | [MT](https://api.globalping.io/v1/measurements/2aaHppJUfUGiYIK0r00021MuA) |
| Monaco | Timeout | No country-local probes available | — |
| North Macedonia | Timeout | 200, 200 | [MK](https://api.globalping.io/v1/measurements/2g2kl1efjiNmxgUky00021MuC) |
| Norway | 403 | 200, 200 | [NO](https://api.globalping.io/v1/measurements/24DqfRwYGzPe4mUnU00021MuA) |
| Romania | Timeout | TCP timeout, TCP timeout | [RO](https://api.globalping.io/v1/measurements/2Voqsh4U7KzBQXwQo00021MuA) |
| Russia | Timeout | TCP timeout, TCP timeout | [RU](https://api.globalping.io/v1/measurements/23oRbyyFZLUatyfwQ00021MuA) |
| Slovenia | 200 | 200, 200 | [SI](https://api.globalping.io/v1/measurements/2lUcFQRGIHX8Wp7on00021MuC) |
| San Marino | 200 | No country-local probes available | — |
| Ukraine | 200 | 200, 200 | [UA](https://api.globalping.io/v1/measurements/22e9mKjnnocicHVPv00021MuA) |

Globalping controls the probes' user agent, and the WARP and country-local tests are different networks and agents. Most probes are hosted on datacenter networks. These checks establish reachability from those specific IPs only. In particular, a Maltese IP did **not** solve Malta's 403 while the Netherlands WARP exit did. Cloudflare WARP [cannot select or spoof an exit country](https://developers.cloudflare.com/warp-client/warp-modes/).

Next diagnosis: for sources with a country-local `200`, test the publisher's feed or archive API and build a date-bounded collector; for 403 challenge responses, seek an official feed/API or publisher access; for timeouts, repeat from independent networks and inspect DNS/TLS/TCP separately. Do not mark an inaccessible section as having published nothing.
