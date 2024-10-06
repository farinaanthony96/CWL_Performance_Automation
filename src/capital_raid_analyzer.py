from cwl_performance_analyzer import COC_API_TOKEN,COC_BASE_API_URL,COC_CLAN_TAG

import urllib.parse

import requests


class Player:
    
    def __init__(self, name: str, tag: str):
        self.name = name
        self.tag = tag
    
    def __eq__(self, other):
        return self.tag == other.tag


def get_raid_weekend_participants(clan_tag: str):
    # Encode the clan tag
    encoded_clan_tag = urllib.parse.quote(clan_tag)
    raid_weekend_response = requests.get(url=f"{COC_BASE_API_URL}/clans/{encoded_clan_tag}/capitalraidseasons",
                                         headers={
                                             "Accept": "application/json",
                                             "Authorization": f"Bearer {COC_API_TOKEN}"
                                         }
    )
    
    # Convert the response to JSON and return it.
    raid_weekend_json = raid_weekend_response.json()
    participants = list[Player]()
    for participant in raid_weekend_json['items'][0]['members']:
        player = Player(participant['name'], participant['tag'])
        participants.append(player)
    
    return participants


def get_clan_members(clan_tag: str) -> list[Player]:
    # Encode the clan tag
    encoded_clan_tag = urllib.parse.quote(clan_tag)
    clan_info_response = requests.get(url=f"{COC_BASE_API_URL}/clans/{encoded_clan_tag}",
                                         headers={
                                             "Accept": "application/json",
                                             "Authorization": f"Bearer {COC_API_TOKEN}"
                                         }
    )
    
    # Convert the response to a list of clan members.
    clan_info_json = clan_info_response.json()
    members = list[Player]()
    for member in clan_info_json['memberList']:
        player = Player(member['name'], member['tag'])
        members.append(player)
    
    return members


def print_non_participants(raid_weekend_participants: list[Player], clan_members: list[Player]) -> None:
    non_participants = clan_members
    for participant in raid_weekend_participants:
        try:
            non_participants.remove(participant)
        except ValueError:
            print(f'{participant.name} (No longer in clan, changed name, or only recently joined the clan)')
    
    # Print the non_participants.
    for non_participant in non_participants:
        print(non_participant.name)


def main():
    raid_weekend_participants = get_raid_weekend_participants(COC_CLAN_TAG)
    
    clan_members = get_clan_members(COC_CLAN_TAG)
    
    print_non_participants(raid_weekend_participants, clan_members)


if __name__ == "__main__":
    main()
