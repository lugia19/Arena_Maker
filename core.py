import copy
import math
import os
import re
import shutil
import subprocess
import json
from typing import Union, List
import xmltodict
from PIL import Image, ImageOps
import soundfile as sf

with open(os.path.join("resources", "constants.json"), "r") as f:
    constants = json.load(f)

paths = {}

baseline_ac = constants["baseline_ac"]
base_talk_accountid = constants["base_talk_accountid"]
menu_category = constants["menu_category"]
param_name_prefix = constants["param_name_prefix"]
starting_arena_id = constants["starting_arena_id"]
starting_arena_rank = constants["starting_arena_rank"]
starting_account_id = constants["starting_account_id"]
starting_npc_chara_id = constants["starting_npc_chara_id"]


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
        json.dump(self.soundbank_data, open(self.soundbank_json_path, "w"), indent=2)

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
        xml_data = xmltodict.parse(open(param_file_path).read())
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

        with open(os.path.join(xml_path), "w") as file:
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

        xml_data = xmltodict.parse(open(fmg_file_path).read())
        self.fmg_text_data = xml_data

    def add_text_fmg_entry(self, id_list: Union[int, List[int]], text_value: str):
        if isinstance(id_list, int):
            id_list = [id_list]

        fmg_entries = self.fmg_text_data["fmg"]["entries"]["text"]

        for item in fmg_entries:
            if item["@id"] in id_list:
                item["#text"] = text_value
                id_list.pop(item["@id"])

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

        with open(os.path.join(fmg_file_path), "w") as file:
            file.write(xml_data)
        run_witchy(fmg_file_path)

class DummySignal:
    def emit(self, arg, arg2):
        return arg

def process_image(subfolder_path, filename, target_width, target_height, pad_x=0, pad_y=0):
    image_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.tiff', ".dds"]

    #Ensure multiple of 4
    if pad_x == 0:
        target_width = target_width + (4 - target_width % 4) % 4
    if pad_y == 0:
        target_height = target_height + (4 - target_height % 4) % 4

    for ext in image_extensions:
        img_path = os.path.join(subfolder_path, f"{filename}{ext}")
        if os.path.exists(img_path):
            break
    else:
        return None  # Image not found

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
    paths["fights_directory"] = os.path.expanduser("~\\AppData\\Roaming\\lugia19\\Arena-Maker")
    paths["ffdec_path"] = os.path.join(resources_dir, "ffdec", "ffdec.bat")
    paths["rewwise_path"] = os.path.join(resources_dir, "rewwise")
    paths["conversion_script_path"] = os.path.join("wem_conversion.py")
    paths["texconv_path"] = os.path.join(resources_dir, "texconv.exe")
    paths["fnv_hash_path"] = os.path.join(paths["rewwise_path"], "fnv-hash.exe")
    paths["bnk2json_path"] = os.path.join(paths["rewwise_path"], "bnk2json.exe")
    paths["game_directory"] = config["game_folder"]
    paths['mod_directory'] = config["mod_folder"]

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
    progress_signal.emit(0, "Adding parameters for fight 1")
    for fight_index, subfolder_path in enumerate(fight_dirs):
        npc_chara_id = starting_npc_chara_id + fight_index
        arena_id = starting_arena_id + fight_index
        account_id = starting_account_id + fight_index * 10

        # Load data.json as a dictionary
        data_file = os.path.join(subfolder_path, "data.json")
        with open(data_file, "r") as file:
            fight_data = json.load(file)

        # Get the path to the .design file
        design_files = [file for file in os.listdir(subfolder_path) if file.endswith(".design")]
        if len(design_files) == 1:
            design_file = os.path.join(subfolder_path, design_files[0])
        elif len(design_files) > 1:
            raise ValueError(f"Multiple .design files found in {subfolder_path}")
        else:
            raise FileNotFoundError(f"No .design file found in {subfolder_path}")

        # Get the path to the .lua file (if needed)
        lua_file = None
        if "logicId" not in fight_data:
            lua_files = [file for file in os.listdir(subfolder_path) if file.endswith(".lua")]

            if len(lua_files) == 1:
                lua_file = os.path.join(subfolder_path, lua_files[0])
            elif len(lua_files) > 1:
                raise ValueError(f"Multiple .lua files found in {subfolder_path}")
            else:
                raise ValueError(f"You did not include a logicId nor a custom lua file in {subfolder_path}")

        decal_thumbnail_path = process_image(subfolder_path, "decal_thumbnail", 128, 128)
        if os.path.exists(decal_thumbnail_path):
            decal_thumbnail_paths[account_id] = decal_thumbnail_path
        rank_icon_path = process_image(subfolder_path, "rank_icon", 232, 128)
        if os.path.exists(rank_icon_path):
            rank_icon_paths[starting_arena_rank - fight_index] = rank_icon_path
        else:
            rank_icon_path = None

        # ArenaParam
        new_fight = {
            "@id": arena_id,
            "@rankTextureId": starting_arena_rank - fight_index if rank_icon_path else 50,
            "@paramdexName": f"{param_name_prefix} Combatant #{fight_index + 1}",
            "@accountParamId": account_id,
            "@charaInitParamId": npc_chara_id,
            "@npcParamId": npc_chara_id,
            "@npcThinkParamId": npc_chara_id,
            "@menuCategory": menu_category,
            **{f"@{key}": value for key, value in fight_data["arenaData"].items()}
        }
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
        if "introLines" in fight_data["textData"]:
            for i in range(3):
                new_talk = {
                    "@id": 600000000 + account_id * 1000 + 100 + i,
                    "@paramdexName": f"{param_name_prefix} Fighter #{fight_index + 1} Intro #{i}",
                    "@msgId": 600000000 + account_id * 1000 + 100 + i,
                    "@voiceId": 600000000 + account_id * 1000 + 100 + i,
                    "@characterNameTextId": fight_data["textData"]["characterNameTextId"]
                }
                talk_param.add_param_entry(new_talk)
                talk_msg_fmg.add_text_fmg_entry(new_talk["@id"], fight_data["textData"]["introLines"][i])

        if "outroLines" in fight_data["textData"]:
            for i in range(2):
                new_talk = {
                    "@id": 700000000 + account_id * 1000 + i,
                    "@paramdexName": f"{param_name_prefix} Fighter #{fight_index + 1} Outro #{i}",
                    "@msgId": 700000000 + account_id * 1000 + i,
                    "@voiceId": 700000000 + account_id * 1000 + i,
                    "@characterNameTextId": fight_data["textData"]["characterNameTextId"]
                }
                talk_param.add_param_entry(new_talk)
                talk_msg_fmg.add_text_fmg_entry(new_talk["@id"], fight_data["textData"]["outroLines"][i])

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
        process_emblem_archetype_images(subfolder_path, account_id, npc_chara_id)

        # Logic file
        if lua_file:
            process_custom_logic_file(lua_file, npc_chara_id)

        process_audio_files(subfolder_path, account_id, npc_015_bnk)
        progress_signal.emit(math.floor(75 / len(fight_dirs) * (fight_index+1)), f"Adding parameters for {fight_index+2}")

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
    open(os.path.join(tpf_dir, "_witchy-tpf.xml"), "w").write(old_witchy_content)

    # Decal thumbnail
    if len(decal_thumbnail_paths.values()) > 0:
        progress_signal.emit(80, "Adding decal thumbnails...")
        combined_texture_sheet, combined_layout = create_texture_sheet(decal_thumbnail_paths, "SB_CustomDecalThumbnails", "SB_DecalThumbnails", 128, 128, "Decal_tmb", 8,
                                                                       existing_texture_sheet=Image.open(os.path.join(tpf_dir, "SB_DecalThumbnails.dds")),
                                                                       existing_layout=xmltodict.parse(open(os.path.join(sblytbnd_dir, "SB_DecalThumbnails.layout")).read()))

        combined_texture_sheet.save(os.path.join(tpf_dir, "SB_DecalThumbnails.png"))

        subprocess.run([paths["texconv_path"], "-f", "BC7_UNORM", os.path.join(tpf_dir, "SB_DecalThumbnails.png"), "-o", tpf_dir, "-y"], check=True)

        with open(os.path.join(sblytbnd_dir, "SB_DecalThumbnails.layout"), "w") as fp:
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
        with open(layout_path, "w") as fp:
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

def process_emblem_archetype_images(subfolder_path, account_id, npc_chara_id):
    copy_file_from_game_folder_if_missing(os.path.join("menu", "hi", "00_solo.tpfbhd"))
    if copy_file_from_game_folder_if_missing(os.path.join("menu", "hi", "00_solo.tpfbdt")):
        run_witchy(os.path.join(paths['mod_directory'], "menu", "hi", "00_solo.tpfbdt"))
    solo_dir = os.path.join(paths['mod_directory'], "menu", "hi", "00_solo-tpfbdt")

    image_paths = []

    decal_image_path = process_image(subfolder_path, "decal", 1024, 1024)
    if os.path.exists(decal_image_path):
        image_paths.append(decal_image_path)

    archetype_image_path = process_image(subfolder_path, "archetype", 2048, 893, pad_y=131)
    if os.path.exists(archetype_image_path):
        image_paths.append(archetype_image_path)


    for image_path in image_paths:
        image_id = str(account_id) if "decal.dds" in image_path else str(npc_chara_id)
        image_id = image_id.zfill(8)

        image_type = "Decal" if "decal" in image_path else "Archetype"
        image_dir = os.path.join(solo_dir, f"MENU_{image_type}_{image_id}-tpf-dcx")
        os.makedirs(image_dir)
        shutil.copy(image_path, os.path.join(image_dir, f"MENU_{image_type}_{image_id}.dds"))

        tpf_dict = generate_single_tpf_xml(f"MENU_{image_type}_{image_id}")
        tpf_xml = xmltodict.unparse(tpf_dict, pretty=True)
        with open(os.path.join(image_dir, "_witchy-tpf.xml"), 'w') as file:
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
    open(lua_file_dest, "w").write(curr_lua_content)

    luagnl_dict = generate_luagnl(npc_chara_id)
    with open(os.path.join(luabnd_dir, f"{npc_chara_id}_logic.luagnl.xml"), 'w') as file:
        file.write(xmltodict.unparse(luagnl_dict, pretty=True))
    run_witchy(os.path.join(luabnd_dir, f"{npc_chara_id}_logic.luagnl.xml"))

    bnd_dict = generate_lua_bnd_xml(npc_chara_id)
    with open(os.path.join(luabnd_dir, "_witchy-bnd4.xml"), 'w') as file:
        file.write(xmltodict.unparse(bnd_dict, pretty=True))
    run_witchy(luabnd_dir)

def process_audio_files(subfolder_path, account_id, soundbnk):
    audio_subfolders = []
    intro_audio_path = os.path.join(subfolder_path, "intro")
    if os.path.exists(intro_audio_path):
        audio_subfolders.append(intro_audio_path)

    outro_audio_path = os.path.join(subfolder_path, "outro")
    if os.path.exists(outro_audio_path):
        audio_subfolders.append(outro_audio_path)

    for audio_subfolder_path in audio_subfolders:
        for filename in os.listdir(audio_subfolder_path):
            if filename.lower().endswith((".wav", ".mp3", ".ogg", ".flac")):
                match = re.match(r'^(\d+)\.\w+$', filename)
                if not match or int(match.group(1)) > 3:
                    print(f"Skipping file '{filename}' as it doesn't follow the naming pattern or the number is greater than 3.")
                    continue

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

                offset = int(os.path.splitext(filename)[0])
                talk_id = 600000000 + int(account_id) * 1000 + 100 + offset if os.path.basename(os.path.dirname(audio_filepath)).lower() == "intro" else 700000000 + int(account_id) * 1000 + offset

                new_wem_filename = str(get_hash(f"Source_v{talk_id}")) + ".wem"
                new_wem_filepath = os.path.join(soundbnk.soundbank_dir, new_wem_filename)
                os.makedirs(os.path.dirname(new_wem_filepath), exist_ok=True)

                if os.path.exists(new_wem_filepath):
                    print(f"Warning - overwriting existing file {new_wem_filename}.")
                shutil.move(audio_filepath.replace(".wav", ".wem"), new_wem_filepath)

                if wav_filename.lower() != filename.lower():
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

    with open(layout_file, 'r') as file:
        xml_data1 = file.read()

    layout_data = xmltodict.parse(xml_data1)

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

    with open(xml_file, 'r') as file:
        xml_data2 = file.read()

    gfx_data = xmltodict.parse(xml_data2)

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
    with open(edited_xml_file, 'w') as file:
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


def copy_file_from_game_folder_if_missing(relative_file_path:str) -> bool:
    destination_file = os.path.join(paths['mod_directory'], relative_file_path)
    os.makedirs(os.path.dirname(destination_file), exist_ok=True)
    if not os.path.exists(destination_file):
        shutil.copy(os.path.join(paths["game_directory"], relative_file_path), destination_file)
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

    # Read the XML file
    with open(xml_file, 'r') as file:
        xml_data = file.read()

    # Parse the XML data into a dictionary
    data_dict = xmltodict.parse(xml_data)

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
    with open(xml_file, 'w') as file:
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