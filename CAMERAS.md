# Public camera rotation

Public YouTube camera candidates. Only streams that pass current live, embedding and playback checks enter the rotation. Videos are embedded directly; EIIM does not download, record, analyse or store camera footage. Availability can change.

| Country | City / view | Operator | Original stream |
|---|---|---|---|
| United Kingdom | London — Abbey Road crossing | EarthCam | [Watch](https://www.youtube.com/watch?v=zMCea32gpmg) |
| France | Paris — Sacré-Cœur, Montmartre | PARIS TV | [Watch](https://www.youtube.com/watch?v=-xzg3wujOVM) |
| Netherlands | Amsterdam — Dam Square | Now4Rent | [Watch](https://www.youtube.com/watch?v=Gd9d4q6WvUY) |
| Ireland | Dublin — Cabra Road | LivefromIreland - Live Streaming Webcams | [Watch](https://www.youtube.com/watch?v=8bqXtRoleVw) |
| Estonia | Tallinn — City centre | 360PANO | [Watch](https://www.youtube.com/watch?v=VhVgZi2lGv0) |
| Finland | Rovaniemi — Santa Claus Village square | City of Rovaniemi | [Watch](https://www.youtube.com/watch?v=Cp4RRAEgpeU) |
| Norway | Hellesylt — Town centre | hellesylt.info | [Watch](https://www.youtube.com/watch?v=ndhYKVzCIs8) |
| Italy | Assisi — Basilica di San Francesco square | Umbria Webcam | [Watch](https://www.youtube.com/watch?v=5ka3YhVZgME) |
| Spain | Reus — Plaça Mercadal | Reus_cat (Ajuntament de Reus) | [Watch](https://www.youtube.com/watch?v=L9HyLjRVN8E) |
| Russia | Saint Petersburg — Palace Bridge | Mobotix Webcams Russia | [Watch](https://www.youtube.com/watch?v=CjtIYbmVfck) |
| Germany | Bremen — Market Square | Visit Bremen | [Watch](https://www.youtube.com/watch?v=SsyiWrkUjy4) |
| Czech Republic | Prague — Charles Bridge and Vltava riverfront | CamStreamer | [Watch](https://www.youtube.com/watch?v=kvYMIaXclIE) |
| Belgium | Mechelen — Grote Markt | Stad Mechelen | [Watch](https://www.youtube.com/watch?v=LnNN3k_Rk7o) |
| Belgium | Sint-Niklaas — Grote Markt | Stad Sint-Niklaas | [Watch](https://www.youtube.com/watch?v=7gOLLJGudNo) |
| Poland | Warsaw — city view | Warsaw Livestream | [Watch](https://www.youtube.com/watch?v=bb-hTtjpXUA) |
| Russia | Saint Petersburg — Nevsky Avenue | Mobotix Webcams Russia | [Watch](https://www.youtube.com/watch?v=w_Dg2vC0tUE) |
| Portugal | Lisbon — airport | AVIAÇÃO TV | [Watch](https://www.youtube.com/watch?v=zVNOlDHh4lk) |
| Italy | Venice — Ponte delle Guglie | I Love You Venice | [Watch](https://www.youtube.com/watch?v=mt7uE-n0YPI) |

Two side panels rotate every 60 and 75 seconds. Active countries cannot repeat across panels. A stream that fails to start or buffers for 22 seconds is skipped and cooled down for five minutes; autoplay restrictions instead show a manual start button. A camera marked offline in the directory stays out until a later verified check reports it live again.

Every two hours a camera-only Pages refresh checks the YouTube Data API and each live candidate's public watch-page playback status. The latter catches an offline slate even when YouTube still reports `isLiveNow=true`. It preserves the latest published research export and makes no Supabase request. Open pages re-fetch the directory every five minutes, so recovered streams rejoin without a browser reload. A failed availability check does not replace the last published directory; individual streams with uncertain playback are excluded. These checks fetch metadata and HTML, never video or audio media.

Live city views provide visual context only. They are not part of the research dataset or evidence of military activity.

The source feed cycles retained observations, pauses on hover/focus, and keeps the collection week visible. Motion can be paused. Reduced-motion preferences disable automatic source cycling and camera rotation by default.
