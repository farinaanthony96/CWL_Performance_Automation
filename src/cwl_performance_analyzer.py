import coc_api_schema.currentwar_leaguegroup as CWLGroup
import coc_api_schema.clanwarleagues_wars as CWLWar

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import os
import urllib.parse

from dotenv import load_dotenv
import gspread,gspread.utils
from gspread_formatting import *
import pandas as pd
import requests


# ====================== Environment / Global Variables =======================
load_dotenv(override=True)

# Initialize Clash of Clans constant global variables.
COC_API_TOKEN = os.getenv("COC_API_TOKEN")
COC_BASE_API_URL = "https://api.clashofclans.com/v1"
COC_CLAN_TAG = os.getenv("COC_CLAN_TAG")
COC_MAX_TOWNHALL_LEVEL = 16
COC_NO_WAR_TAG = "#0"

# Initialize Google Sheets constant global variables.
GOOGLE_SHEETS_SHEET_NAME = datetime.today().strftime("%B")
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")

# Initialize other constant global variables.
CWL_DATA_FILE_PATH = f"./cwl_data/{datetime.today().strftime("%Y_%m")}_cwl_performance_data.csv"


# =========================== Enumerations / Classes ===========================
class AttackRating(Enum):
    """
    Represents the rating of an attack in CWL.
    """
    
    GODLY = "GODLY"
    EXCELLENT = "EXCELLENT"
    ABOVE_AVERAGE = "ABOVE AVERAGE"
    AVERAGE = "AVERAGE"
    BELOW_AVERAGE = "BELOW AVERAGE"
    POOR = "POOR"
    TOO_EASY = "TOO EASY"
    UNKNOWN = "UNKNOWN RATING"


class ParticipationState(Enum):
    """
    Represents the state of a player's participation in a CWL war.
    """
    
    PREPARING = "PREPARING"
    AWAITING_ATTACK = "AWAITING ATTACK"
    ATTACKED = "ATTACKED"
    DID_NOT_ATTACK = "DID NOT ATTACK"
    NOT_IN_WAR = "NOT IN WAR"
    NOT_IN_CLAN = "NOT IN CLAN"
    UNKNOWN = "UNKNOWN STATE"


@dataclass
class Attack:
    stars: int
    destruction_percentage: int
    duration: int
    attacker_map_position: int
    opponent_townhall_level: int
    opponent_map_position: int
    rating: AttackRating
    
    def __str__(self) -> str:
        if self.attacker_map_position != self.opponent_map_position:
            return f"{self.destruction_percentage}% {self.stars}* vs a TH{self.opponent_townhall_level} (ATKD {self.opponent_map_position})"
        
        return f"{self.destruction_percentage}% {self.stars}* vs a TH{self.opponent_townhall_level}"


@dataclass
class WarParticipation:
    state: ParticipationState
    attack: Attack | None
    

@dataclass
class PlayerPerformance:
    player: CWLGroup.GroupClanMember
    sorting_position: int
    war_performances: list[WarParticipation] = field(default_factory=list, init=False)
    total_stars: int = field(default=0, init=False)
    total_destruction_percentage: int = field(default=0, init=False)
    total_duration: int = field(default=0, init=False)
    total_participated_attacks: int = field(default=0, init=False)
    total_rounds_placed_into: int = field(default=0, init=False)
    has_participated: bool = field(default=False, init=False)
    
    def add_war_participation(self, war_state: ParticipationState, war_attack: Attack) -> None:
        self.war_performances.append(WarParticipation(war_state, war_attack))
        
        # Check if there is no attack.
        if not war_attack:
            # Make sure we update that this clan member has participated in CWL before.
            if war_state is ParticipationState.PREPARING:
                self.has_participated = True
            elif war_state in {ParticipationState.AWAITING_ATTACK, ParticipationState.ATTACKED, ParticipationState.DID_NOT_ATTACK}:
                self.total_rounds_placed_into += 1
                self.has_participated = True
            
            return
        
        # Update totals based off the attack.
        self.total_stars += war_attack.stars
        self.total_destruction_percentage += war_attack.destruction_percentage
        self.total_duration += war_attack.duration
        self.total_participated_attacks += 1
        self.total_rounds_placed_into += 1
        self.has_participated = True


@dataclass
class CWLAnalysis:
    clan_members: CWLGroup.GroupClan
    available_wars: list[CWLWar.CWLWar]
    total_rounds: int
    performances: dict[str, PlayerPerformance] = field(default_factory=dict, init=False)
    
    def __post_init__(self):
        self.performances = {member.tag:PlayerPerformance(member, self._find_first_map_position(member.tag)) for member in self.clan_members.members}
    
    def add_player_war_performance(self, player_tag: str, war_attack: Attack) -> None:
        self.performances[player_tag].add_war_participation(ParticipationState.ATTACKED, war_attack)
    
    def add_player_war_state(self, player_tag: str, war_state: ParticipationState) -> None:
        self.performances[player_tag].add_war_participation(war_state, None)
    
    def _find_first_map_position(self, player_tag: str) -> int:
        for war in self.available_wars:
            for player in war.clan.members:
                if player.tag == player_tag:
                    return player.mapPosition
        return 0
    
    
# ================================= Functions =================================
def get_cwl_group(clan_tag: str) -> CWLGroup.CWLGroup:
    """
    Return the CWL group data for the specified clan as a hard-typed object.
    
    Args:
        clan_tag (str): The clan tag of the specified clan.
    
    Returns:
        CWLGroup.CWLGroup: The CWL group object for the specified clan.
    """
    
    # Encode the clan tag, get the clan CWL data from the Clash of Clans API,
    # and return the hard-typed clan CWL object from the response.
    encoded_clan_tag = urllib.parse.quote(clan_tag)
    cwl_group_response = requests.get(url=f"{COC_BASE_API_URL}/clans/{encoded_clan_tag}/currentwar/leaguegroup",
                                      headers={
                                          "Accept": "application/json",
                                          "Authorization": f"Bearer {COC_API_TOKEN}"
                                          }
                                      )
    
    # Check if this clan is done with CWL and have started a new war.
    if cwl_group_response.reason == "Not Found":
        print('CWL information could not be pulled!')
        exit()
    
    cwl_group_json = cwl_group_response.json()
    return CWLGroup.CWLGroup(**cwl_group_json)


def get_cwl_war(war_tag: str, home_clan_tag: str) -> CWLWar.CWLWar:
    """
    Return the war data from a CWL war based off the provided war tag as a hard-typed object.
    
    Args:
        war_tag (str): The war tag of the specific war.
        home_clan_tag (str): The clan tag of the home clan.
    
    Returns:
        CWLWar.CWLWar: The CWL war object for the specified war.
    """
    
    # Encode the war tag, get the war data from the Clash of Clans API, and return the
    # hard-typed war object from the response.
    encoded_war_tag = urllib.parse.quote(war_tag)
    cwl_war_response = requests.get(url=f"{COC_BASE_API_URL}/clanwarleagues/wars/{encoded_war_tag}",
                                    headers={
                                        "Accept": "application/json",
                                        "Authorization": f"Bearer {COC_API_TOKEN}"
                                    }).json()
    return CWLWar.CWLWar(home_clan_tag=home_clan_tag, **cwl_war_response)


def get_home_cwl_wars(rounds: list[CWLGroup.RoundWarTags], home_clan_tag: str) -> list[CWLWar.CWLWar]:
    """
    Return a list of the CWL wars that our home clan was in for all the rounds of CWL.

    Args:
        rounds (list[CWLGroup.RoundWarTags]): A list of all 4 wars happening in a round of CWL.
        home_clan_tag (str): The tag of the clan that we are interested in analyzing (our home clan).

    Returns:
        list[CWLWar.CWLWar]: The list of wars that our home clan was in for CWL.
    """
    
    # TODO: Make this asynchronous.
    # Iterate through each round.
    home_wars = list[CWLWar.CWLWar]()
    for round in rounds:
        # Iterate over each war in this round.
        for war_tag in round.warTags:
            # Check if this war does not have a tag yet.
            if war_tag == COC_NO_WAR_TAG:
                continue
            
            # Get the war data via its war tag.
            cwl_war = get_cwl_war(war_tag, home_clan_tag)
            
            # Check if our home clan is in this war.
            if cwl_war.clan.tag == home_clan_tag:
                home_wars.append(cwl_war)
    
    return home_wars


def rate_attack(attacker: CWLWar.WarClanMember, defender: CWLWar.WarClanMember) -> AttackRating:
    attack = attacker.get_attack()
    rating = AttackRating.UNKNOWN
    
    if attack.stars == 0:
        rating = AttackRating.POOR
    elif defender.townhallLevel == COC_MAX_TOWNHALL_LEVEL:
        if attacker.townhallLevel == COC_MAX_TOWNHALL_LEVEL:
            match attack.stars:
                case 1:
                    rating = AttackRating.BELOW_AVERAGE
                case 2:
                    if 85 <= attack.destructionPercentage <= 99:
                        rating = AttackRating.EXCELLENT
                    elif 70 <= attack.destructionPercentage < 85:
                        rating = AttackRating.ABOVE_AVERAGE
                    else:
                        rating = AttackRating.AVERAGE
                case 3:
                    rating = AttackRating.GODLY
        elif attacker.townhallLevel == COC_MAX_TOWNHALL_LEVEL - 1:
            match attack.stars:
                case 1:
                    rating = AttackRating.AVERAGE
                case 2:
                    if 70 <= attack.destructionPercentage <= 99:
                        rating = AttackRating.EXCELLENT
                    else:
                        rating = AttackRating.ABOVE_AVERAGE
                case 3:
                    rating = AttackRating.GODLY
        elif attacker.townhallLevel <= COC_MAX_TOWNHALL_LEVEL - 2:
            match attack.stars:
                case 1:
                    rating = AttackRating.ABOVE_AVERAGE
                case 2:
                    rating = AttackRating.EXCELLENT
                case 3:
                    rating = AttackRating.GODLY
    elif attacker.townhallLevel == defender.townhallLevel:
        match attack.stars:
            case 1:
                rating = AttackRating.BELOW_AVERAGE
            case 2:
                if 70 <= attack.destructionPercentage <= 99:
                    rating = AttackRating.ABOVE_AVERAGE
                else:
                    rating = AttackRating.AVERAGE
            case 3:
                rating = AttackRating.EXCELLENT
    elif attacker.townhallLevel == defender.townhallLevel + 1:
        match attack.stars:
            case 1:
                rating = AttackRating.POOR
            case 2:
                rating = AttackRating.BELOW_AVERAGE
            case 3:
                rating = AttackRating.AVERAGE
    elif attacker.townhallLevel >= defender.townhallLevel + 2:
        match attack.stars:
            case 3:
                rating = AttackRating.TOO_EASY
            case _:
                rating = AttackRating.POOR
    elif attacker.townhallLevel + 1 == defender.townhallLevel:
        match attack.stars:
            case 1:
                rating = AttackRating.AVERAGE
            case 2:
                if 70 <= attack.destructionPercentage <= 99:
                    rating = AttackRating.EXCELLENT
                else:
                    rating = AttackRating.ABOVE_AVERAGE
            case 3:
                rating = AttackRating.GODLY
    elif attacker.townhallLevel + 2 <= defender.townhallLevel:
        match attack.stars:
            case 1:
                rating = AttackRating.ABOVE_AVERAGE
            case 2:
                rating = AttackRating.EXCELLENT
            case 3:
                rating = AttackRating.GODLY
        
    return rating


def analyze_cwl_performance(cwl_analysis: CWLAnalysis) -> None:
    # Iterate through each available war so far during CWL for the clan.
    for round_index,war in enumerate(cwl_analysis.available_wars):
        # Iterate through each clan member in the clan.
        for clan_member in cwl_analysis.clan_members.members:
            # Check if this clan member is in the war.
            war_member = war.clan.get_war_member(clan_member.tag)
            if not war_member:
                # Member is not in this war.
                print(f"[{war.clan.name}] [Round {round_index + 1}]: {clan_member.name} NOT IN WAR")
                cwl_analysis.add_player_war_state(clan_member.tag, ParticipationState.NOT_IN_WAR)
                continue
            
            # Check if this war member did not attack in this war.
            war_member_attack = war_member.get_attack()
            if not war_member_attack:
                # Check if the war has already ended.
                if war.state == "warEnded":
                    print(f"[{war.clan.name}] [Round {round_index + 1}]: {war_member.name} DID NOT ATTACK")
                    cwl_analysis.add_player_war_state(war_member.tag, ParticipationState.DID_NOT_ATTACK)
                    continue
                # Check if the war is in the preparation period.
                elif war.state == "preparation":
                    print(f"[{war.clan.name}] [Round {round_index + 1}]: {war_member.name} PREPARING")
                    cwl_analysis.add_player_war_state(war_member.tag, ParticipationState.PREPARING)  
                    continue
                # Check if the war is going on right now.
                elif war.state == "inWar":
                    print(f"[{war.clan.name}] [Round {round_index + 1}]: {war_member.name} AWAITING ATTACK")
                    cwl_analysis.add_player_war_state(war_member.tag, ParticipationState.AWAITING_ATTACK)  
                    continue
                # The war is in an unknown / unsupported state...
                else:
                    print(f"[{war.clan.name}] [Round {round_index + 1}]: {war_member.name} UNKNOWN")
                    cwl_analysis.add_player_war_state(war_member.tag, ParticipationState.UNKNOWN)
                    continue
            
            # Analyze the war member's performance!
            opponent = war.opponent.get_war_member(war_member_attack.defenderTag)
            opponent_map_position = war.opponent.get_war_member_map_position(opponent.tag)
            war_member_map_position = war.clan.get_war_member_map_position(war_member.tag)
            attack_rating = rate_attack(war_member, opponent)
            war_member_attack = Attack(war_member_attack.stars, war_member_attack.destructionPercentage, war_member_attack.duration,
                            war_member_map_position, opponent.townhallLevel, opponent_map_position, attack_rating)
            
            # Add the war member's performance to the analysis.
            print(f"[{war.clan.name}] [Round {round_index + 1}]: {war_member.name} " \
                  f"(TH{war_member.townhallLevel}) got a {str(war_member_attack)}")
            cwl_analysis.add_player_war_performance(war_member.tag, war_member_attack)
            
        print("============================================================================")
    
    # Add the "not in war" state to all the wars where there is no data yet.
    remaining_wars = cwl_analysis.total_rounds - len(cwl_analysis.available_wars)
    for _ in range(0, remaining_wars):
        # Add the "not in war" state to all members of the clan.
        for clan_member in cwl_analysis.clan_members.members:
            cwl_analysis.add_player_war_state(clan_member.tag, ParticipationState.NOT_IN_WAR)


def create_data_headers(cwl_analysis: CWLAnalysis) -> list[str]:
    headers = ["Participating Roster", "Townhall Level"]
    
    # Add the appropriate number of rounds to the sheet.
    rounds_remaining = cwl_analysis.total_rounds
    for round_index,round_war in enumerate(cwl_analysis.available_wars):
        if round_war.state == "preparation":
            headers.append(f"War {round_index + 1} Performance\n"
                           f"00* 00.00%   |   00* 00.00%\n"
                           f"0/{round_war.teamSize}        |        0/{round_war.teamSize}")
            rounds_remaining -= 1
            break
        
        headers.append(f"War {round_index + 1} Performance\n{round_war.clan.stars}* {round(round_war.clan.destructionPercentage, 2)}%"
                       f"   |   {round_war.opponent.stars}* {round(round_war.opponent.destructionPercentage, 2)}%\n"
                       f"{round_war.clan.attacks}/{round_war.teamSize}        |        {round_war.opponent.attacks}/{round_war.teamSize}")
        rounds_remaining -= 1
    
    for round_index in range(len(cwl_analysis.available_wars), len(cwl_analysis.available_wars) + rounds_remaining):
        headers.append(f"War {round_index + 1} Performance\n"
                       f"00* 00.00%   |   00* 00.00%\n"
                       f"0/{round_war.teamSize}        |        0/{round_war.teamSize}")
        
        
    headers.append("Attacks Used")
    headers.append("Overall Stars")
    headers.append("Overall Destruction (%)")
    
    return headers


def create_performance_table(cwl_analysis: CWLAnalysis) -> list[list[str]]:
    # Iterate over each clan member to record their performance into a 2D list.
    performance_data_table = list[list[str]]()
    
    # Get a sorted list of players by map position.
    sorted_analysis = sorted(cwl_analysis.performances.values(), key=lambda player_performance: player_performance.sorting_position)
    for participant_performance in sorted_analysis:
        # Check if this clan member participated in CWL.
        if not participant_performance.has_participated:
            continue
        
        # Start with the participant's name and townhall level.
        row = list[str]()
        row.append(participant_performance.player.name)
        row.append(f"TH{participant_performance.player.townHallLevel}")
        
        # Iterate over each of the participant's round performance to add to the row.
        for round_performance in participant_performance.war_performances:
            if not round_performance.attack:
                row.append(round_performance.state.value)
                continue
            
            row.append(str(round_performance.attack))
        
        # Add how many times the participant attacked over how many rounds they were in.
        row.append(f"{participant_performance.total_participated_attacks}/{participant_performance.total_rounds_placed_into}")
        
        # Add how many total stars the participant earned.
        row.append(f"{participant_performance.total_stars}")
        
        # Add how much total destruction % the participant got.
        row.append(f"{participant_performance.total_destruction_percentage}")
        
        performance_data_table.append(row)
    
    return performance_data_table


def create_google_sheet(cwl_analysis: CWLAnalysis, analysis_header: list[str]) -> None:
    gs = gspread.service_account()
    
    cwl_spreadsheet = gs.open_by_key(GOOGLE_SHEETS_SPREADSHEET_ID)
    cwl_worksheet = cwl_spreadsheet.worksheet(GOOGLE_SHEETS_SHEET_NAME)
    format_batch = batch_updater(cwl_spreadsheet)
    
    title_format = CellFormat(textFormat=TextFormat(bold=True), horizontalAlignment='CENTER', verticalAlignment='MIDDLE')
    white_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(1.0, 1.0, 1.0))).to_props()  # Awaiting
    gray_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(0.8, 0.8, 0.8))).to_props()  # Not in war / preparing / war stats
    light_green_2_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(0.714, 0.843, 0.659))).to_props()  # Victory
    light_red_2_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(0.918, 0.6, 0.6))).to_props()  # Defeat
    magenta_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(1.0, 0.0, 1.0))).to_props()  # Godly
    green_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(0.0, 1.0, 0.0))).to_props()  # Excellent
    dark_green_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(0.204, 0.659, 0.325))).to_props()  # Above average
    yellow_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(1.0, 1.0, 0.0))).to_props()  # Average
    orange_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(1.0, 0.6, 0.0))).to_props()  # Below average
    red_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(1.0, 0.0, 0.0))).to_props()  # Poor
    cyan_bg_format = CellFormat(backgroundColorStyle=ColorStyle(rgbColor=Color(0.0, 1.0, 1.0))).to_props()  # Too easy
    format_batch.format_cell_range(cwl_worksheet, "1:2", title_format)
    
    # cwl_worksheet.update_cell(1, 1, f"{cwl_analysis.available_wars[0].clan.name} CWL")
    # cwl_worksheet.update_cell(1, 2, "Opposing Clans =>")
    
    opponent_clan_names = [war.opponent.name for war in cwl_analysis.available_wars]
    opponent_clan_names.extend(["?" for _ in range(0, cwl_analysis.total_rounds - len(opponent_clan_names))])
    cwl_worksheet.update(values=[opponent_clan_names], range_name="C1")
    
    # Attack performance formatting.
    sorted_analysis = sorted(cwl_analysis.performances.values(), key=lambda player_performance: player_performance.sorting_position)
    attack_formatting = list()
    row_num = 3
    for performance in sorted_analysis:
        if not performance.has_participated:
            continue
        
        col_num = 3
        for war_participation in performance.war_performances:
            match war_participation.state:
                case ParticipationState.ATTACKED:
                    match war_participation.attack.rating:
                        case AttackRating.GODLY:
                            attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": magenta_bg_format})
                        case AttackRating.EXCELLENT:
                            attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": green_bg_format})
                        case AttackRating.ABOVE_AVERAGE:
                            attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": dark_green_bg_format})
                        case AttackRating.AVERAGE:
                            attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": yellow_bg_format})
                        case AttackRating.BELOW_AVERAGE:
                            attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": orange_bg_format})
                        case AttackRating.POOR:
                            attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": red_bg_format})
                        case AttackRating.TOO_EASY:
                            attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": cyan_bg_format})
                        case _:
                            attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": gray_bg_format})
                case ParticipationState.AWAITING_ATTACK:
                    attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": white_bg_format})
                case ParticipationState.DID_NOT_ATTACK:
                    attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": red_bg_format})
                case _:
                    attack_formatting.append({"range": gspread.utils.rowcol_to_a1(row_num, col_num), "format": gray_bg_format})
            
            col_num += 1
        
        row_num += 1
    
    # War performance formatting.
    war_performance_formatting = list()
    for round_index,round_war in enumerate(cwl_analysis.available_wars):
        if round_war.state == "preparation":
            continue
        
        if round_war.clan.stars > round_war.opponent.stars:
            war_performance_formatting.append({"range": gspread.utils.rowcol_to_a1(2, round_index + 3), "format": light_green_2_bg_format})
        elif round_war.clan.stars < round_war.opponent.stars:
            war_performance_formatting.append({"range": gspread.utils.rowcol_to_a1(2, round_index + 3), "format": light_red_2_bg_format})
        elif round_war.clan.destructionPercentage > round_war.opponent.destructionPercentage:
            war_performance_formatting.append({"range": gspread.utils.rowcol_to_a1(2, round_index + 3), "format": light_green_2_bg_format})
        elif round_war.clan.destructionPercentage < round_war.opponent.destructionPercentage:
            war_performance_formatting.append({"range": gspread.utils.rowcol_to_a1(2, round_index + 3), "format": light_red_2_bg_format})
        else:
            war_performance_formatting.append({"range": gspread.utils.rowcol_to_a1(2, round_index + 3), "format": white_bg_format})
    
    # Send the war headers to Google sheets.
    cwl_worksheet.update(values=[analysis_header], range_name="A2")
    
    # Make a 2D list of strings of the attack data and send it to Google sheets.
    cwl_performance_table = create_performance_table(cwl_analysis)
    cwl_worksheet.update(values=cwl_performance_table, range_name="A3")
    
    # Send formatting data for the whole sheet to Google sheets.
    format_batch.execute()
    cwl_worksheet.batch_format(attack_formatting)
    
    if len(war_performance_formatting) > 0:
        cwl_worksheet.batch_format(war_performance_formatting)


def main():
    """
    This function will analyze the performance of a clan based off the provided clan tag
    and print the data to the console and a .CSV file.
    """
    
    # Get all the CWL group information.
    cwl_group = get_cwl_group(COC_CLAN_TAG)
    total_rounds = len(cwl_group.rounds)
    
    # Get a reference to our home clan information.
    home_clan = cwl_group.get_clan(COC_CLAN_TAG)
    
    # Get a list of wars that involves our home clan.
    home_wars = get_home_cwl_wars(cwl_group.rounds, COC_CLAN_TAG)
    
    # Analyze the home clan members' CWL performance.
    cwl_analysis = CWLAnalysis(home_clan, home_wars, total_rounds)
    analyze_cwl_performance(cwl_analysis)
    
    # Create the headers for the CWL analysis data.
    headers = create_data_headers(cwl_analysis)
    
    # Create a 2D list of performance data.
    performance_table = create_performance_table(cwl_analysis)
    
    # Print the performance data to the console and to a .CSV file.
    df = pd.DataFrame(performance_table, columns=headers)
    print(df)
    df.to_csv(CWL_DATA_FILE_PATH, index=False)
    
    # Push the performance data to Google sheets.
    create_google_sheet(cwl_analysis, headers)
    

if __name__ == "__main__":
    main()
