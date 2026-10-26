// web/apps/web/src/pages/story/import/sampleWorld.ts
// 시험용 세계관 "시험 마을". 행동 여섯 가지(이동, 시간 보내기, 하루 마치기, 선택지, 건네기, 고백)와 엔딩 둘을 다 거쳐 볼 수 있다.
// asset 서버의 WorldCreate 와 게시 검사(app/worlds/publishing.py)를 통과하고, story 서버의 엔진으로 세 길을 돌려 봤다(2026-10-26):
//   - 카페로 가서 꽃 둘을 건네면(호감도 20 → 60) 고백이 성공해 "함께하는 봄"
//   - 저녁에 공원으로 가면 "소나기"가 열리고, 우산을 함께 쓰면 +20
//   - 하루를 세 번 마치면 기한의 엔딩 "혼자의 여름"
// 인물의 character_id 는 넣기 화면에서 내 캐릭터로 바꾼다(게시한 판이 있는 chat 캐릭터여야 한다).

export const SAMPLE_WORLD: Record<string, unknown> = {
  "name": "시험 마을",
  "rating": "all",
  "deadline_days": 3,
  "after_ending": "end",
  "start_slot": "morning",
  "start_place": "square",
  "places": [
    {
      "id": "square",
      "name": "광장",
      "description": "마을 한가운데의 작은 광장. 분수가 있다."
    },
    {
      "id": "cafe",
      "name": "카페",
      "description": "하나가 일하는 작은 카페."
    },
    {
      "id": "park",
      "name": "공원",
      "description": "저녁이면 사람이 드문 공원."
    }
  ],
  "paths": [
    {
      "a": "square",
      "b": "cafe",
      "minutes": 10
    },
    {
      "a": "square",
      "b": "park",
      "minutes": 20
    }
  ],
  "items": [
    {
      "id": "flower",
      "name": "꽃",
      "description": "광장에서 산 노란 꽃."
    },
    {
      "id": "letter",
      "name": "편지",
      "description": "아직 건네지 못한 편지."
    }
  ],
  "start_items": [
    {
      "item": "flower",
      "count": 2
    },
    {
      "item": "letter",
      "count": 1
    }
  ],
  "cast": [
    {
      "id": "hana",
      "character_id": "00000000-0000-0000-0000-000000000000",
      "home": "cafe",
      "schedule": [
        {
          "slot": "evening",
          "place": "park"
        }
      ],
      "affection": {
        "start": 20,
        "stages": [
          {
            "name": "친구",
            "at": 0
          },
          {
            "name": "호감",
            "at": 40
          },
          {
            "name": "사랑",
            "at": 60
          }
        ],
        "gifts": [
          {
            "id": "flower",
            "item": "flower",
            "change": 20
          },
          {
            "id": "letter",
            "item": "letter",
            "change": 10,
            "once": true
          }
        ]
      },
      "confession": {
        "stage": "사랑",
        "on_fail": "continue",
        "fail_drop": 10,
        "cooldown_days": 1
      }
    }
  ],
  "events": [
    {
      "id": "rain",
      "name": "소나기",
      "when": {
        "match": "all",
        "items": [
          {
            "kind": "reach_place",
            "target": "park"
          },
          {
            "kind": "slot_is",
            "target": "evening"
          }
        ]
      },
      "scene": {
        "text": "공원에 갑자기 소나기가 쏟아진다. 하나는 우산이 없다.",
        "cast": [
          "hana"
        ]
      },
      "choices": [
        {
          "id": "share",
          "text": "우산을 함께 쓴다",
          "effects": [
            {
              "kind": "affection",
              "target": "hana",
              "amount": 20
            }
          ]
        },
        {
          "id": "run",
          "text": "함께 뛰어간다",
          "effects": [
            {
              "kind": "affection",
              "target": "hana",
              "amount": 5
            }
          ]
        }
      ]
    }
  ],
  "endings": [
    {
      "id": "together",
      "name": "함께하는 봄",
      "trigger": {
        "kind": "confess_success",
        "target": "hana"
      },
      "scene": {
        "text": "하나가 고백을 받아들인다. 둘은 봄을 함께 맞기로 한다.",
        "cast": [
          "hana"
        ]
      }
    },
    {
      "id": "alone",
      "name": "혼자의 여름",
      "trigger": {
        "kind": "deadline"
      },
      "scene": {
        "text": "사흘이 지나 마을을 떠난다. 하나에게 마음을 전하지 못했다."
      }
    }
  ]
};
