// web/apps/web/src/api/types.ts
// 화면이 쓰는 서버의 타입에 짧은 이름을 붙인다. 모양은 모두 서버의 API 목록에서 만든 것(generated)이다.
// 손으로 쓴 타입을 두지 않는다(docs/product/screens.md 의 "프런트 구조").

import type { components as Asset } from './generated/asset';
import type { components as Auth } from './generated/auth';
import type { components as Chat } from './generated/chat';
import type { components as Trpg } from './generated/trpg';

export type LoginChallenge = Auth['schemas']['LoginChallenge'];
export type LoginResponse = Auth['schemas']['LoginResponse'];
export type Me = Auth['schemas']['Me'];
export type ConsentState = Auth['schemas']['ConsentState'];
export type ConsentStates = Auth['schemas']['ConsentStates'];

export type PublicNames = Auth['schemas']['PublicNames'];

export type PublicListingPage = Trpg['schemas']['PublicListingPage'];
export type PublicListing = Trpg['schemas']['PublicListing'];
export type PublicListingDetail = Trpg['schemas']['PublicListingDetail'];
export type ListingPregen = Trpg['schemas']['ListingPregen'];
export type Genre = Trpg['schemas']['Genre'];
export type CharacterMode = Trpg['schemas']['CharacterMode'];
export type RecommendedPlayers = Trpg['schemas']['RecommendedPlayers'];
export type NarrationModels = Trpg['schemas']['NarrationModelsOut'];
export type NarrationModel = Trpg['schemas']['NarrationModelOut'];
export type TablePage = Trpg['schemas']['TablePage'];
export type TableSummary = Trpg['schemas']['TableSummary'];
export type TableDetail = Trpg['schemas']['TableDetail'];
export type TableCreate = Trpg['schemas']['TableCreate'];
export type NarrationStyle = Trpg['schemas']['NarrationStyle'];
export type TableMember = Trpg['schemas']['MemberOut'];
export type CharacterUpdate = Trpg['schemas']['CharacterUpdate'];
export type Ruleset = Trpg['schemas']['Ruleset'];
export type PregenChoice = Trpg['schemas']['PregenChoice'];
export type AbilityRoll = Trpg['schemas']['RollOut'];
export type TableEvent = Trpg['schemas']['EventOut'];
export type EventPage = Trpg['schemas']['EventPage'];
export type ChatMessage = Trpg['schemas']['MessageOut'];
export type MessagePage = Trpg['schemas']['MessagePage'];
export type WhisperPage = Trpg['schemas']['WhisperPage'];

export type PublicCharacterPage = Asset['schemas']['PublicCharacterPage'];
export type PublicCharacterSummary = Asset['schemas']['PublicCharacterSummary'];

export type ConversationPage = Chat['schemas']['ConversationPage'];
export type ConversationSummary = Chat['schemas']['ConversationSummary'];
