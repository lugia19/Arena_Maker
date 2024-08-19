import copy
import math
import os
import re
import shutil
import subprocess
import json
import zipfile
from typing import Union, List

import numpy
import xmltodict
from PIL import ImageDraw, ImageFont, ImageColor, Image, ImageOps, ImageFilter

import soundfile as sf

FIGHTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fights")
os.makedirs(FIGHTS_FOLDER, exist_ok=True)
paths = {}

baseline_ac = 11200000
base_talk_accountid = 310
menu_category = 20
param_name_prefix = "CustomArena"
starting_arena_id = 300
starting_arena_rank = 300
starting_account_id = 16000
starting_npc_chara_id = 999009800


en_jp_fmg_filenames = {
        "TalkMsg": {
            "file":"menu.msgbnd.dcx",
            "name":"会話"
        },
        "RankerProfile": {
            "file":"menu.msgbnd.dcx",
            "name":"ランカープロフィール"
        },
        "TitleCharacters": {
            "file":"item.msgbnd.dcx",
            "name":"NPC名"
        },
        "MenuText": {
            "file":"menu.msgbnd.dcx",
            "name":"FNR_メニューテキスト"
        }
    }


# Define the rank data
rank_tiers = [
    {"letter": "S", "percentage": 10, "color": "#fff145"},
    {"letter": "A", "percentage": 15, "color": "#83eeee"},
    {"letter": "B", "percentage": 20, "color": "#7744b2"},
    {"letter": "C", "percentage": 25, "color": "#0bc367"},
    {"letter": "D", "percentage": 10, "color": "#853322"},
    {"letter": "E", "percentage": 10, "color": "#e3ffff"},
    {"letter": "F", "percentage": 10, "color": "#e3ffff"},
]

class SoundbankEditor:
    def __init__(self, rel_soundbank_path):
        copy_file_from_game_folder_if_missing(rel_soundbank_path)
        soundbank_path = os.path.join(paths['mod_directory'], rel_soundbank_path)
        subprocess.run([paths["bnk2json_path"], soundbank_path])
        self.soundbank_path = soundbank_path
        self.soundbank_dir = os.path.join(os.path.dirname(soundbank_path), os.path.splitext(soundbank_path)[0])
        self.soundbank_json_path = os.path.join(self.soundbank_dir, "soundbank.json")

        self.soundbank_data = json.load(open(self.soundbank_json_path, "r"))
        self.sound_object_list = self.soundbank_data["sections"][1]["body"]["HIRC"]["objects"]

        self.base_play_event = copy.deepcopy(self.get_object(f"Play_v{600000000 + base_talk_accountid * 1000 + 100}"))
        self.base_play_action = copy.deepcopy(self.get_object(self.base_play_event["body"]["Event"]["actions"][0]))
        self.base_stop_event = copy.deepcopy(self.get_object(f"Stop_v{600000000 + base_talk_accountid * 1000 + 100}"))
        self.base_stop_action = copy.deepcopy(self.get_object(self.base_stop_event["body"]["Event"]["actions"][0]))
        self.base_sound = copy.deepcopy(self.get_object(self.base_stop_action["body"]["Action"]["external_id"]))
        self.actor_mixer = self.get_object(self.base_sound["body"]["Sound"]["node_base_params"]["direct_parent_id"])

    def get_object(self, object_id: Union[str, int]):
        if isinstance(object_id, str):
            hash_id = get_hash(object_id)
            string_id = object_id
        else:
            hash_id = object_id
            string_id = "nonexistant"
        for snd_object in self.sound_object_list:
            if snd_object["id"].get("Hash") == hash_id or snd_object["id"].get("String") == string_id:
                return snd_object

        return None

    def update_sound(self, talk_id: int, sound_filename: str):
        string_id = f"Sound_v{talk_id}"
        new_sound = self.get_object(string_id)

        if not new_sound:
            new_sound = copy.deepcopy(self.base_sound)
            new_sound["id"]["Hash"] = get_hash(string_id)
            self.sound_object_list.insert(self.sound_object_list.index(self.base_sound), new_sound)

        new_sound["body"]["Sound"]["bank_source_data"]["source_type"] = "Embedded"
        new_sound["body"]["Sound"]["bank_source_data"]["media_information"]["source_id"] = int(sound_filename.replace(".wem", ""))

        if new_sound["id"]["Hash"] not in self.actor_mixer["body"]["ActorMixer"]["children"]["items"]:
            self.actor_mixer["body"]["ActorMixer"]["children"]["items"].append(new_sound["id"]["Hash"])

        return new_sound["id"]["Hash"]

    def add_action(self, talk_id: int, is_play: bool, sound_filename: str):
        base_action = self.base_play_action if is_play else self.base_stop_action
        string_id = f"{'Play_' if is_play else 'Stop_'}Action_v{talk_id}"

        new_action = self.get_object(string_id)
        if not new_action:
            new_action = copy.deepcopy(base_action)
            new_action["id"]["Hash"] = get_hash(string_id)
            self.sound_object_list.insert(self.sound_object_list.index(base_action), new_action)

        sound_hash = self.update_sound(talk_id, sound_filename)
        new_action["body"]["Action"]["external_id"] = sound_hash

        return new_action["id"]["Hash"]

    def add_event(self, talk_id: int, is_play: bool, sound_filename: str):
        prefix = "Play_" if is_play else "Stop_"
        base_event = self.base_play_event if is_play else self.base_stop_event

        event_string_id = f"{prefix}v{talk_id}"
        new_event = self.get_object(event_string_id)
        if not new_event:
            new_event = copy.deepcopy(base_event)
            if "Hash" in new_event["id"]:
                new_event["id"].pop("Hash")
            new_event["id"]["String"] = event_string_id
            self.sound_object_list.insert(self.sound_object_list.index(base_event), new_event)

        new_action_id = self.add_action(talk_id, is_play, sound_filename)
        new_event["body"]["Event"]["actions"] = [new_action_id]

        return new_event["id"]["String"]

    def save(self):
        print(f'Final ActorMixer children count: {len(self.actor_mixer["body"]["ActorMixer"]["children"]["items"])}')
        print(f'Final object count: {len(self.sound_object_list)}')
        json.dump(self.soundbank_data, open(self.soundbank_json_path, "w", encoding="utf-8"), indent=2)

        print("Done saving. Rebuilding the bnk from the folder.")
        subprocess.run([paths["bnk2json_path"], self.soundbank_dir])
        shutil.move(self.soundbank_path, self.soundbank_path.replace(".bnk", ".backup.bnk"))
        shutil.move(self.soundbank_path.replace(".bnk",".created.bnk"), self.soundbank_path)

class ParamFile:
    def __init__(self, param_name, baseline_id: Union[int, str], baseline_id_property="@id"):
        self.param_name = param_name
        self.baseline_id = baseline_id
        self.baseline_id_property = baseline_id_property
        self.param_data = None
        self.base_data = None
        self.fetch_param_xml()

    def fetch_param_xml(self):
        if copy_file_from_game_folder_if_missing("regulation.bin"):
            run_witchy(os.path.join(paths['mod_directory'], "regulation.bin"), recursive=True)

        param_file_path = os.path.join(os.path.join(paths['mod_directory'], "regulation-bin"), self.param_name + ".param.xml")
        xml_data = parse_xml_file(param_file_path)
        self.param_data = xml_data
        self.base_data = self.get_param_entry_with_id(self.baseline_id, self.baseline_id_property)

    def get_param_entry_with_id(self, ID: Union[int, str], ID_property="@id"):
        for entry in self.param_data["param"]["rows"]["row"]:
            if entry[ID_property] == str(ID):
                return copy.deepcopy(entry)
        return None

    def add_param_entry(self, new_param_entry_data: dict):
        new_param_entry = copy.deepcopy(self.base_data)
        for key, value in new_param_entry_data.items():
            new_param_entry[key] = value

        param_rows = self.param_data["param"]["rows"]["row"]

        insert_index = None
        for i in range(len(param_rows)):
            if int(new_param_entry["@id"]) < int(param_rows[i]["@id"]):
                insert_index = i
                break

        if insert_index is None:
            param_rows.append(new_param_entry)
        else:
            param_rows.insert(insert_index, new_param_entry)

    def save(self):
        xml_file = self.param_name + ".param.xml"
        xml_path = os.path.join(paths['mod_directory'], "regulation-bin", xml_file)
        xml_data = xmltodict.unparse(self.param_data, pretty=True)

        with open(os.path.join(xml_path), "w", encoding="utf-8") as file:
            file.write(xml_data)
        run_witchy(xml_path)

class FMGFile:
    def __init__(self, fmg_name):
        self.fmg_name = fmg_name
        self.fmg_text_data = None
        self.fetch_fmg_text()

    def fetch_fmg_text(self):
        bnds = ["menu.msgbnd.dcx", "item.msgbnd.dcx"]
        msg_rel_dir = os.path.join("msg", "engus")
        for bnd in bnds:
            if copy_file_from_game_folder_if_missing(os.path.join(msg_rel_dir, bnd)):
                run_witchy(os.path.join(paths['mod_directory'], msg_rel_dir, bnd), recursive=True)

        msgdir = os.path.join(paths['mod_directory'], msg_rel_dir)
        actual_fmg_name = en_jp_fmg_filenames[self.fmg_name]["name"]
        fmg_file_path = os.path.join(msgdir, en_jp_fmg_filenames[self.fmg_name]["file"].replace(".", "-"), actual_fmg_name + ".fmg.xml")
        xml_data = parse_xml_file(fmg_file_path)
        self.fmg_text_data = xml_data

    def add_text_fmg_entry(self, id_list: Union[int, List[int]], text_value: str):
        if isinstance(id_list, int):
            id_list = [id_list]

        fmg_entries:List = self.fmg_text_data["fmg"]["entries"]["text"]
        items_to_pop = []
        for item in fmg_entries:
            if int(item["@id"]) in id_list:
                items_to_pop.append(item)
        for item in items_to_pop:
            fmg_entries.pop(item)
        for item_id in id_list:
            fmg_entries.append({"@id": item_id, "#text": text_value})

    def save(self):
        bnds = ["menu.msgbnd.dcx", "item.msgbnd.dcx"]
        msg_rel_dir = os.path.join("msg", "engus")
        for bnd in bnds:
            if copy_file_from_game_folder_if_missing(os.path.join(msg_rel_dir, bnd)):
                run_witchy(os.path.join(msg_rel_dir, bnd), recursive=True)

        msgdir = os.path.join(paths['mod_directory'], msg_rel_dir)
        actual_fmg_name = en_jp_fmg_filenames[self.fmg_name]["name"]
        fmg_file_path = os.path.join(msgdir, en_jp_fmg_filenames[self.fmg_name]["file"].replace(".", "-"), actual_fmg_name + ".fmg.xml")

        xml_data = xmltodict.unparse(self.fmg_text_data, pretty=True)

        with open(os.path.join(fmg_file_path), "w", encoding="utf-8") as file:
            file.write(xml_data)
        run_witchy(fmg_file_path)

class DummySignal:
    def emit(self, arg, arg2):
        return arg

def parse_xml_file(filepath):
    with open(filepath, 'r', encoding="utf-8") as file:
        xml_data = file.read()
    first_tag_index = xml_data.find('<')
    if first_tag_index != -1:
        xml_data = xml_data[first_tag_index:]

    xml_dict = None
    try:
        xml_dict = xmltodict.parse(xml_data)
    except Exception as e:
        e.args = ("Error parsing XML file",filepath) + e.args
        raise e
    return xml_dict

def generate_rank_image(text, text_color, font_path):
    image_size = (232, 128)
    text_size = (155, 55)  # for 2 digits
    if len(text.split("/")[0]) > 2:
        text_size = (180, 55)  # For 3 digits
    glow_size = 20
    font_size = 70
    glow_iterations = 3
    text_color = ImageColor.getcolor(text_color, mode="RGB")

    # Create a transparent image
    image = Image.new('RGBA', image_size, (0, 0, 0, 0))

    # Load the font with fixed size
    font = ImageFont.truetype(font_path, font_size)

    # Create a temporary image for the text
    temp_img = Image.new('RGBA', (1000, 1000), (0, 0, 0, 0))  # Large temporary image
    temp_draw = ImageDraw.Draw(temp_img)

    # Draw text on temporary image
    temp_draw.text((0, 0), text, font=font, fill=text_color)

    # Crop the temporary image to the text bounds
    text_bbox = temp_img.getbbox()
    temp_img = temp_img.crop(text_bbox)

    # Resize (stretch) the text image to fit the specified text_size
    stretched_text = temp_img.resize(text_size, Image.LANCZOS)

    # Calculate text position in the main image (centered)
    text_position = ((image_size[0] - text_size[0]) // 2, (image_size[1] - text_size[1]) // 2)

    # Create the text layer
    text_layer = Image.new('RGBA', image_size, (0, 0, 0, 0))
    text_layer.paste(stretched_text, text_position)

    # Create glow effect
    glow_layer = text_layer.copy()
    for i in range(glow_iterations):
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(glow_size / glow_iterations))

        glow_layer_colored = Image.new('RGBA', image_size, text_color + (0,))
        glow_layer = Image.composite(glow_layer_colored, glow_layer, glow_layer)

        image = Image.alpha_composite(image, glow_layer)

    # Add the original text on top
    image = Image.alpha_composite(image, text_layer)

    return image

def process_image(subfolder_path, img_path, target_width, target_height, pad_x=0, pad_y=0):
    if not img_path:
        return None
    if subfolder_path not in img_path:
        img_path = os.path.join(subfolder_path, img_path)
    #Ensure multiple of 4
    if pad_x == 0:
        target_width = target_width + (4 - target_width % 4) % 4
    if pad_y == 0:
        target_height = target_height + (4 - target_height % 4) % 4

    filename = os.path.splitext(os.path.basename(img_path))[0]
    resized_img_path = os.path.join(subfolder_path, f"{filename}-resized.png")
    with Image.open(img_path) as img:
        # Resize the image
        img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        img_resized = ImageOps.expand(img_resized, (0, 0, pad_x, pad_y))

        # Save the padded image
        img_resized.save(resized_img_path)

    # Convert to DDS using texconv
    dds_path = os.path.join(subfolder_path, f"{filename}-final.dds")

    subprocess.run([paths["texconv_path"], "-f", "BC7_UNORM", resized_img_path, "-o", subfolder_path, "-y"], check=True)
    shutil.move(os.path.join(subfolder_path, f"{filename}-resized.dds"), dds_path)
    os.remove(os.path.join(subfolder_path, f"{filename}-resized.png"))
    return dds_path


def compile_folder(progress_signal=None):
    with open("config.json", "r") as f:
        config = json.load(f)

    if not progress_signal:
        progress_signal = DummySignal()

    resources_dir = os.path.join(os.path.dirname(__file__), "resources")
    paths["witchybnd_path"] = os.path.join(resources_dir, "witchybnd", "WitchyBND.exe")
    paths["fights_directory"] = FIGHTS_FOLDER
    paths["ffdec_path"] = os.path.join(resources_dir, "ffdec", "ffdec.bat")
    paths["rewwise_path"] = os.path.join(resources_dir, "rewwise")
    paths["conversion_script_path"] = os.path.join("wem_conversion.py")
    paths["texconv_path"] = os.path.join(resources_dir, "texconv.exe")
    paths["fnv_hash_path"] = os.path.join(paths["rewwise_path"], "fnv-hash.exe")
    paths["bnk2json_path"] = os.path.join(paths["rewwise_path"], "bnk2json.exe")
    paths["game_directory"] = config["game_folder"]
    paths["wem_converter"] = os.path.join(resources_dir, "wem_converter.exe")
    paths["mod_directory"] = os.path.join(os.path.dirname(resources_dir), "mod")

    try:
        shutil.rmtree(paths['mod_directory'])
        print(f"Directory '{paths['mod_directory']}' and its contents have been deleted.")
    except FileNotFoundError:
        print(f"Directory '{paths['mod_directory']}' does not exist.")
    os.makedirs(paths['mod_directory'], exist_ok=True)

    # Prep params
    arena_param = ParamFile("ArenaParam", baseline_ac, "@charaInitParamId")
    charinit_param = ParamFile("CharaInitParam", baseline_ac)
    npc_param = ParamFile("NpcParam", baseline_ac)
    account_param = ParamFile("AccountParam", npc_param.base_data["@accountParamId"])
    npcthink_param = ParamFile("NpcThinkParam", baseline_ac)
    talk_param = ParamFile("TalkParam", 600000000 + int(npc_param.base_data["@accountParamId"]) * 1000 + 100)

    # Prep FMGs
    menu_text_fmg = FMGFile("MenuText")
    menu_text_fmg.add_text_fmg_entry([258010 + menu_category], "CUSTOM ARENA")
    ranker_profile_fmg = FMGFile("RankerProfile")
    title_characters_fmg = FMGFile("TitleCharacters")
    talk_msg_fmg = FMGFile("TalkMsg")

    decal_thumbnail_paths = dict()
    rank_icon_paths = dict()

    npc_015_bnk = SoundbankEditor(os.path.join("sd", "enus", "npc015.bnk"))

    # Main loop
    fight_order = config["folder_order"]
    fight_dirs = [os.path.join(paths["fights_directory"], fight_dir) for fight_dir in fight_order]
    total_fights = len(fight_dirs)

    # Calculate the number of fights for each rank
    fights_per_rank = [math.ceil(tier["percentage"] * total_fights / 100) for tier in rank_tiers]

    # Ensure we have at least one fight per used rank
    while sum(fights_per_rank) > total_fights:
        fights_per_rank[-1] -= 1
        if fights_per_rank[-1] == 0:
            fights_per_rank.pop()

    progress_signal.emit(0, f"Adding parameters for fight 1/{total_fights}")
    for fight_index, subfolder_path in enumerate(fight_dirs):
        npc_chara_id = starting_npc_chara_id + fight_index
        arena_id = starting_arena_id + fight_index
        account_id = starting_account_id + fight_index * 10

        # Load data.json as a dictionary
        data_file = os.path.join(subfolder_path, "data.json")
        with open(data_file, "r") as file:
            fight_data = json.load(file)

        file_data = fight_data["fileData"]
        # Get the path to the .design file
        design_file = os.path.join(subfolder_path, file_data["acDesign"])

        # Get the path to the .lua file (if present)
        lua_file = None
        if "logicFile" in file_data:
            lua_file = os.path.join(subfolder_path, file_data["logicFile"])

        if "decalThumbnail" in file_data:
            decal_thumbnail_path = process_image(subfolder_path, file_data["decalThumbnail"], 128, 128)
            if decal_thumbnail_path:
                decal_thumbnail_paths[account_id] = decal_thumbnail_path

        rank_data = None
        rank_icon_path = None
        # In your loop, replace the rank_data section with this:
        if "rankIcon" in file_data:
            rank_icon_path = process_image(subfolder_path, os.path.join(subfolder_path, file_data["rankIcon"]), 232, 128)
        elif "customRankData" in fight_data:
            rank_data = fight_data["customRankData"]
        else:
            # Calculate the rank number (1 is the highest rank)
            rank_number = total_fights - fight_index
            rank_letter = ""
            rank_color = "#ffffff"
            # Determine which rank tier this fight belongs to
            cumulative_fights = 0
            for i, fights in enumerate(fights_per_rank):
                cumulative_fights += fights
                if rank_number <= cumulative_fights:
                    rank_letter = rank_tiers[i]["letter"]
                    rank_color = rank_tiers[i]["color"]
                    break
            if rank_number < 10:
                rank_number = f"0{rank_number}"
            rank_data = {
                "text": f"{rank_number}/{rank_letter}",
                "color": rank_color
            }

        if rank_data:
            rank_icon_img = generate_rank_image(rank_data["text"], rank_data["color"], os.path.join(resources_dir, "Jura-SemiBold.ttf"))
            rank_icon_path = os.path.join(subfolder_path, f"{fight_index}_rank_icon.png")
            rank_icon_img.save(rank_icon_path)
            rank_icon_path = process_image(subfolder_path, rank_icon_path, 232, 128)
            os.remove(os.path.join(subfolder_path, f"{fight_index}_rank_icon.png")) #Clean up

        rank_icon_paths[starting_arena_rank - fight_index] = rank_icon_path

        default_arena_values = {
            "introCutsceneId": "230000",
            "outroCutsceneId": -1,
        }

        # ArenaParam
        new_fight = {
            "@id": arena_id,
            "@rankTextureId": starting_arena_rank - fight_index,
            "@paramdexName": f"{param_name_prefix} Combatant #{fight_index + 1}",
            "@accountParamId": account_id,
            "@charaInitParamId": npc_chara_id,
            "@npcParamId": npc_chara_id,
            "@npcThinkParamId": npc_chara_id,
            "@menuCategory": menu_category,
            **{f"@{key}": value for key, value in fight_data["arenaData"].items()}
        }
        for key, value in default_arena_values.items():
            if key not in fight_data["arenaData"]:
                new_fight[key] = value

        arena_param.add_param_entry(new_fight)
        ranker_profile_fmg.add_text_fmg_entry(new_fight["@id"], fight_data["textData"]["arenaDescription"])

        # AccountParam
        new_account = {
            "@paramdexName": f"{param_name_prefix} Account #{fight_index + 1}",
            "@id": account_id,
            "@fmgId": account_id,
            "@menuDecalId": account_id
        }
        account_param.add_param_entry(new_account)
        title_characters_fmg.add_text_fmg_entry([account_id, account_id + 2], fight_data["textData"]["acName"])
        title_characters_fmg.add_text_fmg_entry([account_id + 1, account_id + 3], fight_data["textData"]["pilotName"])

        # Intro and Outro text
        if "intro" in fight_data["textData"]:
            for i in range(3):
                new_talk = {
                    "@id": 600000000 + account_id * 1000 + 100 + i,
                    "@paramdexName": f"{param_name_prefix} Fighter #{fight_index + 1} Intro #{i}",
                    "@msgId": 600000000 + account_id * 1000 + 100 + i,
                    "@voiceId": 600000000 + account_id * 1000 + 100 + i,
                    "@characterNameTextId": fight_data["textData"].get("characterNameTextId", "200")
                }
                talk_param.add_param_entry(new_talk)
                talk_msg_fmg.add_text_fmg_entry(new_talk["@id"], fight_data["textData"]["intro"][i])

        if "outro" in fight_data["textData"]:
            for i in range(2):
                new_talk = {
                    "@id": 700000000 + account_id * 1000 + i,
                    "@paramdexName": f"{param_name_prefix} Fighter #{fight_index + 1} Outro #{i}",
                    "@msgId": 700000000 + account_id * 1000 + i,
                    "@voiceId": 700000000 + account_id * 1000 + i,
                    "@characterNameTextId": fight_data["textData"].get("characterNameTextId", "200")
                }
                talk_param.add_param_entry(new_talk)
                talk_msg_fmg.add_text_fmg_entry(new_talk["@id"], fight_data["textData"]["outro"][i])

        # CharaInitParam
        new_charainit = {
            "@paramdexName": f"{param_name_prefix} CharaInit #{fight_index + 1}",
            "@id": npc_chara_id,
            "@acDesignId": npc_chara_id
        }
        charinit_param.add_param_entry(new_charainit)

        # NpcParam
        new_npcparam = {
            "@paramdexName": f"{param_name_prefix} NpcParam #{fight_index + 1}",
            "@id": npc_chara_id,
            "@accountParamId": account_id
        }
        npc_param.add_param_entry(new_npcparam)

        # NpcThinkParam
        new_npcthinkdata = {
            "@paramdexName": f"{param_name_prefix} NpcThink #{fight_index + 1}",
            "@id": npc_chara_id,
            "@logicId": npc_chara_id if lua_file else fight_data["logicId"]
        }
        npcthink_param.add_param_entry(new_npcthinkdata)

        # Design file
        add_design_file(design_file, npc_chara_id)

        # Emblem/archetype
        process_emblem_archetype_images(subfolder_path, account_id, npc_chara_id, file_data)

        # Logic file
        if lua_file:
            os.makedirs(os.path.join(paths['mod_directory'], "script"), exist_ok=True)
            if not os.path.exists(os.path.join(paths['mod_directory'], "script", "aicommon.luabnd.dcx")):
                shutil.copy(os.path.join(resources_dir, "aicommon.luabnd.dcx"), os.path.join(paths['mod_directory'], "script"))
            process_custom_logic_file(lua_file, npc_chara_id)

        process_audio_files(subfolder_path, account_id, npc_015_bnk, file_data)
        progress_signal.emit(math.floor(75 / len(fight_dirs) * (fight_index+1)), f"Adding parameters for fight {fight_index+2}/{total_fights}")

    progress_signal.emit(75, "Unpacking textures...")
    # Prep work for thumbnails and rank icons
    sblytbnd_path = os.path.join("menu", "hi", "01_common.sblytbnd.dcx")
    copy_file_from_game_folder_if_missing(sblytbnd_path)
    sblytbnd_dir = os.path.join(paths['mod_directory'], sblytbnd_path.replace(".", "-"))
    sblytbnd_path = os.path.join(paths['mod_directory'], sblytbnd_path)
    run_witchy(sblytbnd_path)

    tpf_path = os.path.join("menu", "hi", "01_common.tpf.dcx")
    copy_file_from_game_folder_if_missing(tpf_path)
    tpf_dir = os.path.join(paths['mod_directory'], tpf_path.replace(".", "-"))
    tpf_path = os.path.join(paths['mod_directory'], tpf_path)
    run_witchy(tpf_path)

    old_witchy_content = open(os.path.join(tpf_dir, "_witchy-tpf.xml")).read().replace("DCX_KRAK_MAX", "DCX_DFLT_11000_44_9_15")
    open(os.path.join(tpf_dir, "_witchy-tpf.xml"), "w", encoding="utf-8").write(old_witchy_content)

    # Decal thumbnail
    if len(decal_thumbnail_paths.values()) > 0:
        progress_signal.emit(80, "Adding decal thumbnails...")
        combined_texture_sheet, combined_layout = create_texture_sheet(decal_thumbnail_paths, "SB_CustomDecalThumbnails", "SB_DecalThumbnails", 128, 128, "Decal_tmb", 8,
                                                                       existing_texture_sheet=Image.open(os.path.join(tpf_dir, "SB_DecalThumbnails.dds")),
                                                                       existing_layout=parse_xml_file(os.path.join(sblytbnd_dir, "SB_DecalThumbnails.layout")))

        combined_texture_sheet.save(os.path.join(tpf_dir, "SB_DecalThumbnails.png"))

        subprocess.run([paths["texconv_path"], "-f", "BC7_UNORM", os.path.join(tpf_dir, "SB_DecalThumbnails.png"), "-o", tpf_dir, "-y"], check=True)

        with open(os.path.join(sblytbnd_dir, "SB_DecalThumbnails.layout"), "w", encoding="utf-8") as fp:
            fp.write(xmltodict.unparse(combined_layout, pretty=True))
        for path in decal_thumbnail_paths.values():
            os.remove(path)

    # Rank icons
    if len(rank_icon_paths.values()) > 0:
        progress_signal.emit(85, "Adding custom rank icons...")
        new_rank_sheet, rank_layout = create_texture_sheet(rank_icon_paths, "SB_CustomArenaRank", "SB_ArenaRank", 232, 128, "CustomArenaRank", 5)
        new_rank_sheet.save(os.path.join(tpf_dir, "SB_CustomArenaRank.png"))
        subprocess.run([paths["texconv_path"], "-f", "BC7_UNORM", os.path.join(tpf_dir, "SB_CustomArenaRank.png"), "-o", tpf_dir, "-y"], check=True)

        layout_path = os.path.join(sblytbnd_dir, "SB_CustomArenaRank.layout")
        with open(layout_path, "w", encoding="utf-8") as fp:
            fp.write(xmltodict.unparse(rank_layout, pretty=True))

        add_to_witchy_xml(sblytbnd_dir, ["SB_CustomArenaRank.layout"])
        add_to_witchy_xml(tpf_dir, ["SB_CustomArenaRank.dds"])

        # GFX wizardry
        gfx_files = ["01_texteffect_hi.gfx", "02_acarena_preparing.gfx", "02_acarena_select.gfx", "02_npcarenaresult.gfx"]
        for gfx_file in gfx_files:
            copy_file_from_game_folder_if_missing(os.path.join("menu", gfx_file))
            process_gfx_file(os.path.join(paths['mod_directory'], "menu", gfx_file), layout_path)

        for path in rank_icon_paths.values():
            os.remove(path)
    progress_signal.emit(95, "Saving...")
    # Save params
    arena_param.save()
    charinit_param.save()
    npc_param.save()
    account_param.save()
    npcthink_param.save()
    talk_param.save()
    run_witchy(os.path.join(paths['mod_directory'], "regulation-bin"))

    # Save FMGs
    menu_text_fmg.save()
    ranker_profile_fmg.save()
    title_characters_fmg.save()
    talk_msg_fmg.save()
    npc_015_bnk.save()
    run_witchy(os.path.join(paths['mod_directory'], "msg", "engus", "item-msgbnd-dcx"))
    run_witchy(os.path.join(paths['mod_directory'], "msg", "engus", "menu-msgbnd-dcx"))
    run_witchy(os.path.join(paths['mod_directory'], "param", "asmparam", "asmparam-designbnd-dcx"))
    run_witchy(tpf_dir)
    run_witchy(sblytbnd_dir)
    progress_signal.emit(100, "Done!")

def process_emblem_archetype_images(subfolder_path, account_id, npc_chara_id, file_data):
    copy_file_from_game_folder_if_missing(os.path.join("menu", "hi", "00_solo.tpfbhd"))
    if copy_file_from_game_folder_if_missing(os.path.join("menu", "hi", "00_solo.tpfbdt")):
        run_witchy(os.path.join(paths['mod_directory'], "menu", "hi", "00_solo.tpfbdt"))
    solo_dir = os.path.join(paths['mod_directory'], "menu", "hi", "00_solo-tpfbdt")

    image_paths = []

    decal_image_path = process_image(subfolder_path, file_data.get("decalImage"), 1024, 1024)
    if decal_image_path:
        image_paths.append(decal_image_path)

    archetype_image_path = process_image(subfolder_path, file_data.get("archetypeImage"), 2048, 893, pad_y=131)
    if archetype_image_path:
        image_paths.append(archetype_image_path)


    for image_path in image_paths:
        image_type = "Decal" if image_path == file_data.get("decalImage") else "Archetype"
        image_id = str(account_id) if image_type == "Decal" else str(npc_chara_id)
        image_id = image_id.zfill(8)


        image_dir = os.path.join(solo_dir, f"MENU_{image_type}_{image_id}-tpf-dcx")
        os.makedirs(image_dir, exist_ok=True)
        shutil.copy(image_path, os.path.join(image_dir, f"MENU_{image_type}_{image_id}.dds"))

        tpf_dict = generate_single_tpf_xml(f"MENU_{image_type}_{image_id}")
        tpf_xml = xmltodict.unparse(tpf_dict, pretty=True)
        with open(os.path.join(image_dir, "_witchy-tpf.xml"), 'w', encoding="utf-8") as file:
            file.write(tpf_xml)

        run_witchy(image_dir)
        add_to_witchy_xml(solo_dir, [f"MENU_{image_type}_{image_id}.tpf.dcx"])
        os.remove(image_path)
    run_witchy(solo_dir)

def process_custom_logic_file(lua_file, npc_chara_id):
    current_id = os.path.basename(lua_file).split("_")[0]
    luabnd_dir = os.path.join(paths['mod_directory'], "script", f"{npc_chara_id}_logic-luabnd-dcx")
    lua_file_dest = os.path.join(luabnd_dir, f"{npc_chara_id}_logic.lua")
    os.makedirs(luabnd_dir, exist_ok=True)
    shutil.copy(lua_file, os.path.join(luabnd_dir, f"{npc_chara_id}_logic.lua"))

    curr_lua_content = open(lua_file_dest, "r").read()
    curr_lua_content = curr_lua_content.replace(current_id, str(npc_chara_id))
    open(lua_file_dest, "w", encoding="utf-8").write(curr_lua_content)

    luagnl_dict = generate_luagnl(npc_chara_id)
    with open(os.path.join(luabnd_dir, f"{npc_chara_id}_logic.luagnl.xml"), 'w', encoding="utf-8") as file:
        file.write(xmltodict.unparse(luagnl_dict, pretty=True))
    run_witchy(os.path.join(luabnd_dir, f"{npc_chara_id}_logic.luagnl.xml"))

    bnd_dict = generate_lua_bnd_xml(npc_chara_id)
    with open(os.path.join(luabnd_dir, "_witchy-bnd4.xml"), 'w', encoding="utf-8") as file:
        file.write(xmltodict.unparse(bnd_dict, pretty=True))
    run_witchy(luabnd_dir)

def convert_to_wem(input_file):
    # Get the directory and filename without extension
    input_dir, input_filename = os.path.split(input_file)
    filename_without_ext = os.path.splitext(input_filename)[0]

    # Create a temporary WAV file name
    temp_wav = os.path.join(input_dir, f"{filename_without_ext}_temp.wav")

    try:
        # Read the audio file
        data, samplerate = sf.read(input_file)

        # Convert to stereo if mono
        if len(data.shape) == 1 or data.shape[1] == 1:
            print(f"Converting {input_file} from mono to stereo")
            stereo_data = numpy.column_stack((data, data))
        else:
            print(f"{input_file} is already in stereo")
            stereo_data = data

        # Write the stereo data to the temporary WAV file
        sf.write(temp_wav, stereo_data, samplerate)

        # Run the WEM converter executable
        subprocess.run([paths["wem_converter"], temp_wav], check=True)

        # The output will be temp.wem in the same directory as the executable
        temp_wem = os.path.join(os.getcwd(), "test.wem")

        # Create the final WEM filename
        final_wem = os.path.join(input_dir, f"{filename_without_ext}.wem")

        # Move and rename the temp.wem file
        shutil.move(temp_wem, final_wem)

        print(f"Created WEM file: {final_wem}")
        return final_wem

    finally:
        # Clean up the temporary WAV file if it was created
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
            print(f"Cleaned up temporary file: {temp_wav}")

def process_audio_files(subfolder_path, account_id, soundbnk, file_data):
    intro_audio_paths = file_data.get("introAudioPaths")
    if intro_audio_paths:
        intro_audio_paths = [os.path.join(subfolder_path, x) for x in intro_audio_paths]

    outro_audio_paths = file_data.get("outroAudioPaths")
    if outro_audio_paths:
        outro_audio_paths = [os.path.join(subfolder_path, x) for x in outro_audio_paths]

    for audio_file_list in [intro_audio_paths, outro_audio_paths]:
        if not audio_file_list:
            continue
        for filepath in audio_file_list:

            filename = os.path.basename(filepath)
            if filename.lower().endswith((".wav", ".mp3", ".ogg", ".flac")):
                if False:
                    audio_subfolder_path = os.path.dirname(filepath)
                    wav_filename = os.path.splitext(filename)[0] + ".wav"
                    wav_filepath = os.path.join(audio_subfolder_path, wav_filename)

                    if filename.lower().endswith(".wav"):
                        audio_filepath = os.path.join(audio_subfolder_path, filename)
                    else:
                        audio_data, sample_rate = sf.read(os.path.join(audio_subfolder_path, filename))
                        sf.write(wav_filepath, audio_data, sample_rate, format='WAV')
                        audio_filepath = wav_filepath

                    command = ["python", paths["conversion_script_path"], audio_filepath]
                    subprocess.run(command, check=True)

                wem_file = convert_to_wem(filepath)
                offset = audio_file_list.index(filepath)
                talk_id = 600000000 + int(account_id) * 1000 + 100 + offset if audio_file_list == intro_audio_paths else 700000000 + int(account_id) * 1000 + offset

                new_wem_filename = str(get_hash(f"Source_v{talk_id}")) + ".wem"
                new_wem_filepath = os.path.join(soundbnk.soundbank_dir, new_wem_filename)
                os.makedirs(os.path.dirname(new_wem_filepath), exist_ok=True)

                if os.path.exists(new_wem_filepath):
                    print(f"Warning - overwriting existing file {new_wem_filename}.")
                shutil.move(wem_file, new_wem_filepath)

                if False and wav_filename.lower() != filename.lower():
                    os.remove(wav_filepath)

                soundbnk.add_event(talk_id, is_play=True, sound_filename=new_wem_filename)
                soundbnk.add_event(talk_id, is_play=False, sound_filename=new_wem_filename)

def get_hash(input_text):
    command = [os.path.join(paths["rewwise_path"], "fnv-hash.exe"), "--input", input_text]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return int(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error running the command: {e}")
        print(f"Error output: {e.stderr}")
        return None

def modify_sprite_tag(sprite_tag, images_by_rank, arena_rank_00000d_id):
    last_image_id = max(images_by_rank.keys())
    sub_tags_copy = sprite_tag['subTags']['item'].copy()

    def find_nth_frame_tag_index(n):
        inner_frame_count = 0
        for i, tag in enumerate(sprite_tag['subTags']['item']):
            if tag['@type'] == 'ShowFrameTag':
                inner_frame_count += 1
                if inner_frame_count == n:
                    return i
        return -1

    frame_count = 1
    for sub_tag in sub_tags_copy:
        if sub_tag['@type'] == 'ShowFrameTag':
            if frame_count - 1 in images_by_rank.keys():
                remove_object2_tag = '<item type="RemoveObject2Tag" depth="1" forceWriteAsLong="false"/>'
                place_object3_tag = f'<item type="PlaceObject3Tag" bitmapCache="0" blendMode="0" characterId="{images_by_rank[frame_count - 1]["characterID"]}" clipDepth="0" depth="1" forceWriteAsLong="true" placeFlagHasBlendMode="false" placeFlagHasCacheAsBitmap="false" placeFlagHasCharacter="true" placeFlagHasClassName="false" placeFlagHasClipActions="false" placeFlagHasClipDepth="false" placeFlagHasColorTransform="false" placeFlagHasFilterList="false" placeFlagHasImage="true" placeFlagHasMatrix="true" placeFlagHasName="false" placeFlagHasRatio="false" placeFlagHasVisible="false" placeFlagMove="false" placeFlagOpaqueBackground="false" ratio="0" reserved="false" visible="0">'
                place_object3_tag += '<matrix type="MATRIX" hasRotate="false" hasScale="false" nRotateBits="0" nScaleBits="0" nTranslateBits="13" rotateSkew0="0" rotateSkew1="0" scaleX="0" scaleY="0" translateX="-2320" translateY="-1280"/>'
                place_object3_tag += '</item>'
                index = find_nth_frame_tag_index(frame_count)
                if index != -1:
                    sprite_tag['subTags']['item'].insert(index, xmltodict.parse(remove_object2_tag)['item'])
                    sprite_tag['subTags']['item'].insert(index + 1, xmltodict.parse(place_object3_tag)['item'])

            if frame_count == last_image_id + 2:
                place_object3_tag = f'<item type="PlaceObject3Tag" bitmapCache="0" blendMode="0" characterId="{arena_rank_00000d_id}" clipDepth="0" depth="1" forceWriteAsLong="true" placeFlagHasBlendMode="false" placeFlagHasCacheAsBitmap="false" placeFlagHasCharacter="true" placeFlagHasClassName="false" placeFlagHasClipActions="false" placeFlagHasClipDepth="false" placeFlagHasColorTransform="false" placeFlagHasFilterList="false" placeFlagHasImage="true" placeFlagHasMatrix="true" placeFlagHasName="false" placeFlagHasRatio="false" placeFlagHasVisible="false" placeFlagMove="false" placeFlagOpaqueBackground="false" ratio="0" reserved="false" visible="0">'
                place_object3_tag += '<matrix type="MATRIX" hasRotate="false" hasScale="false" nRotateBits="0" nScaleBits="0" nTranslateBits="13" rotateSkew0="0" rotateSkew1="0" scaleX="0" scaleY="0" translateX="-2320" translateY="-1280"/>'
                place_object3_tag += '</item>'
                index = find_nth_frame_tag_index(frame_count)
                if index != -1:
                    sprite_tag['subTags']['item'].insert(index, xmltodict.parse(place_object3_tag)['item'])

            frame_count += 1
def process_gfx_file(gfx_file, layout_file):
    xml_file = os.path.splitext(gfx_file)[0] + '.xml'
    subprocess.run([paths["ffdec_path"], '-swf2xml', gfx_file, xml_file], check=True)
    layout_data = parse_xml_file(layout_file)

    rank_image_files = []
    item_list = layout_data["TextureAtlas"]['SubTexture']
    if not isinstance(item_list, list):
        item_list = [item_list]

    for item in item_list:
        filename = item['@name']
        id_match = re.search(r'_(\d+)\.png$', filename)
        if id_match:
            id_value = int(id_match.group(1))
            rank_image_files.append({"filename": filename, "rankID": id_value})
    gfx_data = parse_xml_file(xml_file)

    highest_character_id = max([int(item['@characterID']) for item in gfx_data['swf']["tags"]["item"] if '@characterID' in item])
    base_character_id_offset = ((highest_character_id // 100) + 1) * 100

    arena_rank_00000d_id = None
    for item in gfx_data['swf']['tags']['item']:
        if item['@type'] == 'DefineExternalImage2' and item['@exportName'] == 'ArenaRank_00000d':
            arena_rank_00000d_id = int(item['@characterID'])

    if arena_rank_00000d_id is None:
        print("ArenaRank_00000d.tga not found.")
        return

    last_line_index = None
    for i, item in enumerate(gfx_data['swf']["tags"]["item"]):
        if item['@type'] == 'DefineExternalImage2' and 'ArenaRank' in item['@exportName']:
            last_line_index = i

    for idx, image_file_data in enumerate(rank_image_files):
        new_line = f'<item type="DefineExternalImage2" bitmapFormat="13" characterID="{base_character_id_offset + idx}" exportName="{image_file_data["filename"][:-4]}" fileName="{image_file_data["filename"][:-4]}.tga" forceWriteAsLong="false" imageID="{base_character_id_offset + idx}" targetHeight="128" targetWidth="232" unknownID="0"/>'
        rank_image_files[idx]["characterID"] = base_character_id_offset + idx
        gfx_data['swf']["tags"]["item"].insert(last_line_index + 1, xmltodict.parse(new_line)['item'])

    names_by_charID = {}
    for item in gfx_data['swf']['tags']['item']:
        if item['@type'] == 'SymbolClassTag':
            for i in range(len(item["tags"]["item"])):
                names_by_charID[int(item["tags"]["item"][i])] = item["names"]["item"][i]

    sprite_tag = None
    for item in gfx_data['swf']['tags']['item']:
        if item['@type'] == 'DefineSpriteTag':
            character_id = int(item['@spriteId'])
            if "arenarank" in names_by_charID.get(character_id, "").lower():
                sprite_tag = item

    images_by_rank = {image["rankID"]: image for image in rank_image_files}
    modify_sprite_tag(sprite_tag, images_by_rank, arena_rank_00000d_id)

    edited_xml_file = os.path.splitext(gfx_file)[0] + '-edited.xml'
    with open(edited_xml_file, 'w', encoding="utf-8") as file:
        file.write(xmltodict.unparse(gfx_data, pretty=True))

    subprocess.run([paths["ffdec_path"], '-xml2swf', edited_xml_file, gfx_file], check=True)
    os.remove(xml_file)
    os.remove(edited_xml_file)
def create_texture_sheet(image_files: dict, texture_atlas_name, root_texture_atlas_name, subtexture_width, subtexture_height, prefix, id_length: int, gap_size=2, existing_texture_sheet=None, existing_layout=None):
    num_images = len(image_files.values())
    square_size = math.ceil(math.sqrt(num_images))
    num_rows = math.ceil(num_images / square_size)
    num_columns = math.ceil(num_images / num_rows)

    if existing_texture_sheet is None:
        sheet_width = num_columns * subtexture_width + (num_columns - 1) * gap_size
        sheet_height = num_rows * subtexture_height + (num_rows - 1) * gap_size
        texture_sheet = Image.new("RGBA", (sheet_width, sheet_height), (0, 0, 0, 0))
        subtextures = []
    else:
        sheet_width, sheet_height = existing_texture_sheet.size
        texture_sheet = existing_texture_sheet.copy()
        subtextures = existing_layout["TextureAtlas"]["SubTexture"]

    for index, item in enumerate(image_files.items()):
        image_index, image_file = item
        image = Image.open(image_file)

        if image.size != (subtexture_width, subtexture_height):
            raise ValueError(f"Image {image_file} has incorrect dimensions. Expected {subtexture_width}x{subtexture_height}, got {image.size}")

        if existing_texture_sheet is None:
            row = index // num_columns
            col = index % num_columns
            x = col * (subtexture_width + gap_size)
            y = row * (subtexture_height + gap_size)
        else:
            x = sheet_width
            y = 0
            sheet_width += subtexture_width + gap_size

        texture_sheet.paste(image, (x, y))

        subtexture = {
            "@name": f"{prefix}_{str(image_index).zfill(id_length)}.png",
            "@x": str(x),
            "@width": str(subtexture_width),
            "@y": str(y),
            "@height": str(subtexture_height)
        }

        subtextures.append(subtexture)

    # Adjust canvas size to be a multiple of 4
    adjusted_width = sheet_width + sheet_width % 4
    adjusted_height = sheet_height + sheet_height % 4
    adjusted_texture_sheet = Image.new("RGBA", (adjusted_width, adjusted_height), (0, 0, 0, 0))
    adjusted_texture_sheet.paste(texture_sheet, (0, 0))

    texture_atlas = {
        "TextureAtlas": {
            "@imagePath": f"W:\\FNR\\data\\Menu\\ScaleForm\\Tif\\01_Common\\{root_texture_atlas_name}\\Hi\\exp\\{texture_atlas_name}.png",
            "@width": str(adjusted_width),
            "@height": str(adjusted_height),
            "SubTexture": subtextures
        }
    }

    return adjusted_texture_sheet, texture_atlas
def generate_single_tpf_xml(filename):
    tpf_dict = {
        'tpf': {
            'filename': f'{filename}.tpf.dcx',
            'compression': 'DCX_KRAK_MAX',
            'encoding': '0x01',
            'flag2': '0x03',
            'platform': 'PC',
            'textures': {
                'texture': {
                    'name': f'{filename}.dds',
                    'format': '102',
                    'flags1': '0x00'
                }
            }
        }
    }
    return tpf_dict
def generate_luagnl(logic_id):
    luagnl_dict = {
        "luagnl": {
            "filename": f"{logic_id}_logic.luagnl",
            "bigendian": False,
            "longformat": True,
            "globals": {
                "global": [
                    f'LogicInitialSetup_{logic_id}',
                    f'InterruptCallBack_{logic_id}'
                ]
            }
        }
    }

    return luagnl_dict
def generate_lua_bnd_xml(logic_id):
    bnd4_dict = {
        'bnd4': {
            'filename': f'{logic_id}_logic.luabnd.dcx',
            'compression': 'DCX_KRAK_MAX',
            'version': '07D7R6',
            'format': 'IDs, Names1, Names2, Compression',
            'bigendian': 'False',
            'bitbigendian': 'False',
            'unicode': 'True',
            'extended': '0x04',
            'unk04': 'False',
            'unk05': 'False',
            'root': f'W:\\FNR\\data\\Target\\INTERROOT_win64\\script\\ai\\out\\each\\{logic_id}_logic',
            'files': {
                'file': [
                    {
                        'flags': 'Flag1',
                        'id': '1000',
                        'path': f'{logic_id}_logic.lua'
                    },
                    {
                        'flags': 'Flag1',
                        'id': '1000000',
                        'path': f'{logic_id}_logic.luagnl'
                    }
                ]
            }
        }
    }
    return bnd4_dict

def run_exe_shell_hack(exe_path:str, args=None):
    if not args:
        args = []
    try:
        command_dir = os.path.dirname(exe_path)
        command_line = f"\"{exe_path}\" {' '.join(args)}"
        if command_dir == "":
            command_dir = None

        cmd_command = f'start /wait cmd /c "{command_line}"'
        process = subprocess.Popen(
            cmd_command,
            cwd=command_dir,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd_command, output=stdout, stderr=stderr)
    except subprocess.CalledProcessError as error:
        print(f"Error running {os.path.basename(exe_path)}: {error}")
        if error.output:
            print(f"stdout: {error.output.decode()}")
        if error.stderr:
                print(f"stderr: {error.stderr.decode()}")

def run_witchy(path:str, recursive:bool=False):
    #args = ["-p", f"\"{path}\""]
    args = [paths["witchybnd_path"], "-s", path]
    if recursive:
        args.insert(2, "-c")
    subprocess.run(args, check=True, capture_output=True, text=True)
    #run_exe_shell_hack(paths["witchybnd_path"], args)


def copy_file_from_game_folder_if_missing(relative_file_path: str) -> bool:
    resources_dir = os.path.join(os.path.dirname(__file__), "resources")
    game_data_dir = os.path.join(resources_dir, "game_data")

    if not os.path.exists(game_data_dir):
        # Check if game_data.zip exists in the resources directory
        game_data_zip = os.path.join(resources_dir, "game_data.zip")
        if os.path.exists(game_data_zip):
            # Extract game_data.zip to the resources directory
            with zipfile.ZipFile(game_data_zip, 'r') as zip_ref:
                zip_ref.extractall(resources_dir)
        else:
            raise FileNotFoundError("Neither 'game_data' folder nor 'game_data.zip' found in the resources directory.")

    source_file = os.path.join(game_data_dir, relative_file_path)
    destination_file = os.path.join(paths['mod_directory'], relative_file_path)
    os.makedirs(os.path.dirname(destination_file), exist_ok=True)

    if not os.path.exists(destination_file):
        shutil.copy(source_file, destination_file)
        return True
    return False

def add_to_witchy_xml(folder_path:str, new_files:list[str]):
    # Search for an XML file whose name starts with "_witchy"
    xml_file = None
    for file_name in os.listdir(folder_path):
        if file_name.startswith("_witchy") and file_name.endswith(".xml"):
            xml_file = os.path.join(folder_path, file_name)
            break

    if xml_file is None:
        raise FileNotFoundError("No XML file starting with '_witchy' found in the specified folder")

    # Parse the XML data into a dictionary
    data_dict = parse_xml_file(xml_file)
    # Check the root element to determine the XML format
    if 'bnd4' in data_dict or "bxf4" in data_dict:
        # Handle bnd4 format
        root_element = "bnd4" if "bnd4" in data_dict else "bxf4"
        files_element = data_dict[root_element].get('files', {'file': []})
        existing_files = files_element['file'] if isinstance(files_element['file'], list) else [files_element['file']]
        max_id = max([int(file['id']) for file in existing_files], default=-1)

        for new_file in new_files:
            # Check if the file is already present
            if any(file['path'] == new_file for file in existing_files):
                print(f"File '{new_file}' is already present in the XML. Skipping...")
                continue

            max_id += 1
            new_file_element = {
                'flags': 'Flag1',
                'id': str(max_id),
                'path': new_file
            }
            existing_files.append(new_file_element)

        data_dict[root_element]['files'] = {'file': existing_files}

    elif 'tpf' in data_dict:
        # Handle tpf format
        textures_element = data_dict['tpf'].get('textures', {'texture': []})
        existing_textures = textures_element['texture'] if isinstance(textures_element['texture'], list) else [textures_element['texture']]

        for new_file in new_files:
            # Check if the texture is already present
            if any(texture['name'] == new_file for texture in existing_textures):
                print(f"Texture '{new_file}' is already present in the XML. Skipping...")
                continue

            new_texture_element = {
                'name': new_file,
                'format': '102',
                'flags1': '0x00'
            }
            existing_textures.append(new_texture_element)

        data_dict['tpf']['textures'] = {'texture': existing_textures}

    else:
        raise ValueError("Unsupported XML format")

    # Convert the updated dictionary back to XML
    updated_xml = xmltodict.unparse(data_dict, pretty=True)

    # Write the updated XML to the file
    with open(xml_file, 'w', encoding="utf-8") as file:
        file.write(updated_xml)

    print(f"Updated {xml_file} with {len(new_files)} new files")
def add_design_file(design_file_path, design_id:Union[str,int]):
    designbnd_rel_path = os.path.join("param","asmparam","asmparam.designbnd.dcx")
    if copy_file_from_game_folder_if_missing(designbnd_rel_path):
        run_witchy(os.path.join(paths['mod_directory'], designbnd_rel_path))
    design_dir = os.path.join(paths['mod_directory'], designbnd_rel_path.replace(".","-"))
    shutil.copy(design_file_path, os.path.join(design_dir, f"{design_id}.design"))

    add_to_witchy_xml(design_dir, [f"{design_id}.design"])





if __name__=="__main__":
    compile_folder()