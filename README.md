# Arena Maker
This is a tool that allows you to easily share/import custom Arena fights, and will automatically compile them into a mod.

It supports:
- Custom icons (Emblem, Arena preview, etc).
- Custom intro/outro voicelines and text
- Custom BGM (soon tm, waiting for a rewwise update)
- Custom AI

It will automatically download WitchyBND, rewwise, ffdec, texconv.
It also relies on Wwise Studio 2019+ being installed.

## Functionality

Basically, if you click "Import" you will have to give it a zip file containing one or more arena fights.
Each fight should be in its own subfolder, and each fight folder should follow this structure:
## Fight folder structure:
  - data.json: Contains information about the fight itself. Detailed later.
  - [SomethingSomething].design: The AC design file, you can use the [design editor](https://github.com/lugia19/AC6_Design_Editor/releases/).
  - archetype.png (Optional): The Arena Preview image.
  - decal.png: The Emblem shown during the intro.
  - decal_thumbnail.png: The small version of the emblem shown next to the HP bar.
  - rank_icon.png: The rank icon.
  - intro (Optional)
    - 0/1/2.wav: The audio files corresponding to the intro lines.
  - outro (Optional)
    - 0/1.wav: The audio files corresponding to the outro lines.
  - [SomeID]_logic.lua (Optional): A custom AI logic file. If you don't include one, you'll have to specify a logicId in data.json.
  - bgm.wav (Optional): A track that will be used for background music. Currently non-functional, will be implemented at a later date.

Note: Both image files and audio files can be almost any format, they'll be converted accordingly. Additionally, an example fight is included.

## Data.json structure:
- arenaData:
  - initialCoamReward
  - repeatCoamReward
  - missionParamId: The Arena map
  - introCutsceneId
  - outroCutsceneId
  - bgmSoundId
- textData:
  - acName
  - pilotName
  - arenaDescription
  - introLines (Optional): An array that contains the text for the three intro lines.
  - outroLines (Optional): An array that contains the text for the two outro lines.
  - characterNameTextId: The ID of the character speaking the intro/outro lines.
- logicId (Optional): The ID of an existing logic file. Only include it if not using a custom logic file.

