# Arena Maker
This is a tool that allows you to easily share/import custom Arena fights, and will automatically compile them into a mod.

It supports:
- Custom icons (Emblem, Arena preview, etc).
- Custom intro/outro voicelines and text
- Custom BGM (soon tm, waiting for a rewwise update)
- Custom AI

## Requirements

- The game must have been unpacked with UXM.
- Java must be installed for JPEXS decompiler.


It will automatically download other dependencies such as WitchyBND, rewwise, ffdec, texconv.


## Functionality

Basically, if you click "Import" you will have to give it a zip file containing one or more arena fights.

Each fight should be in its own subfolder, and should contain a file called **data.json**.

## Data.json structure:
- arenaData:
  - initialCoamReward: The COAM reward for first time completion.
  - repeatCoamReward: The COAM reward for repeated completions.
  - missionParamId: The Arena map to use for the fight.
  - introCutsceneId (Optional): The ID of the intro cutscene to use. Defaults to 230000, the generic one.
  - outroCutsceneId (Optional): The outro cutscene. No idea if it can cause problems. Default to -1, meaning no cutscene.
  - bgmSoundId: The ID of the background musci to use.
- textData:
  - acName: The name of the AC
  - pilotName: The callsign of the pilot.
  - arenaDescription: The description blurb displayed on the arena screen.
  - intro (Optional): An array that contains the text for the three intro lines.
  - outro (Optional): An array that contains the text for the two outro lines.
  - characterNameTextId (Optional): The ID of the character speaking the intro/outro lines. Defaults to 200, ALLMIND.
- fileData: Contains the various filenames/relative file paths to resources for the fight.
  - acDesign: The AC .design file. You can make it using the [design editor](https://github.com/lugia19/AC6_Design_Editor/releases/).
  - logicFile (Optional): A custom AI logic file. Must be a functional logic file, saved as [SomeID]_logic.lua (with the ID being the one used in the file).
  - customBGM (Optional): A track that will be used for background music. Currently non-functional, will be implemented at a later date.
  - archetypeImage (Optional): The Arena Preview image.
  - decalImage (Optional): The Emblem shown during the intro.
  - decalThumbnail (Optional): The small version of the emblem shown next to the HP bar.
  - rankIcon (Optional): A custom rank icon. If not present, a rnak icon will be generated based on the sorted order.
  - introAudioPaths (Optional): An array that contains the filepaths to the three audio files for the intro lines.
  - outroAudioPaths (Optional): An array that contains the filepaths to the two  audio files for the outro lines.
- customRankData: Allows you to modify the automatically generated rank icon. Ignored if a rankIcon is specified in fileData.
  - text: The text (eg, 100/F).
  - color: The color of the text and glow, in hex (eg, #ffffff).
- logicId: The ID of an existing logic file. Ignored if logicFile is specified in fileData.


Note: Both image files and audio files can be almost any format, they'll be converted accordingly. Additionally, an example fight is included.
