// web/apps/web/src/api/types.ts
// 화면이 쓰는 서버의 타입에 짧은 이름을 붙인다. 모양은 모두 서버의 API 목록에서 만든 것(generated)이다.
// 손으로 쓴 타입을 두지 않는다(docs/product/screens.md 의 "프런트 구조").

import type { components as Asset } from './generated/asset';
import type { components as Auth } from './generated/auth';
import type { components as Billing, operations as BillingOperations } from './generated/billing';
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
// 제작 도구(B9). 재료의 목록은 종류를 가리지 않고 같은 모양이다
export type AssetPage = Trpg['schemas']['AssetPage'];
export type AssetSummary = Trpg['schemas']['AssetSummary'];
export type RulebookDetail = Trpg['schemas']['RulebookDetail'];
export type RulebookCreate = Trpg['schemas']['RulebookCreate'];
export type RulebookUpdate = Trpg['schemas']['RulebookUpdate'];
export type RulebookTemplates = Trpg['schemas']['TemplateList'];
export type RulebookTemplate = Trpg['schemas']['TemplateSummary'];
export type TemplateKey = Trpg['schemas']['Template'];
export type Armor = Trpg['schemas']['Armor'];
export type ArmorMode = Trpg['schemas']['ArmorMode'];
export type WorldDetail = Trpg['schemas']['WorldDetail'];
export type WorldCreate = Trpg['schemas']['WorldCreate'];
export type WorldUpdate = Trpg['schemas']['WorldUpdate'];
export type LorebookCreate = Trpg['schemas']['LorebookCreate'];
export type LorebookUpdate = Trpg['schemas']['LorebookUpdate'];
export type LoreEntry = Trpg['schemas']['EntryDetail'];
export type LoreEntryCreate = Trpg['schemas']['EntryCreate'];
export type LoreEntryUpdate = Trpg['schemas']['EntryUpdate'];
export type LoreKind = Trpg['schemas']['LoreKind'];
export type BestiaryCreate = Trpg['schemas']['BestiaryCreate'];
export type BestiaryUpdate = Trpg['schemas']['BestiaryUpdate'];
export type Monster = Trpg['schemas']['MonsterDetail'];
export type MonsterCreate = Trpg['schemas']['MonsterCreate'];
export type MonsterUpdate = Trpg['schemas']['MonsterUpdate'];
export type MonsterKind = Trpg['schemas']['MonsterKind'];
export type Rating = Trpg['schemas']['Rating'];
export type ScenarioDetail = Trpg['schemas']['ScenarioDetail'];
export type ScenarioCreate = Trpg['schemas']['ScenarioCreate'];
export type ScenarioUpdate = Trpg['schemas']['ScenarioUpdate'];
export type ScenarioClock = Trpg['schemas']['Clock'];
export type ModelStatus = Trpg['schemas']['ModelStatusOut'];
export type PublishCheck = Trpg['schemas']['PublishCheck'];
export type VersionSummary = Trpg['schemas']['VersionSummary'];
export type VersionDetail = Trpg['schemas']['VersionDetail'];
export type ScenarioSheet = Trpg['schemas']['Sheet'];
export type ScenarioPregen = Trpg['schemas']['Pregen-Output'];
export type PregenBody = Trpg['schemas']['Pregen-Input'];
export type PlayerMadeHp = Trpg['schemas']['PlayerMadeHp'];
export type PregenChoice = Trpg['schemas']['PregenChoice'];
export type AbilityRoll = Trpg['schemas']['RollOut'];
export type Round = Trpg['schemas']['RoundOut'];
export type RoundPage = Trpg['schemas']['RoundPage'];
export type Declaration = Trpg['schemas']['DeclarationOut'];
export type DeclarationUpdate = Trpg['schemas']['DeclarationUpdate'];
export type CheckAction = Trpg['schemas']['CheckAction'];
export type CheckOutcome = Trpg['schemas']['CheckOutcome'];
export type DeathSave = Trpg['schemas']['DeathSaveOut'];
export type Sheet = Trpg['schemas']['SheetOut'];
export type SheetInjury = Trpg['schemas']['InjuryOut'];
export type HeldItem = Trpg['schemas']['ItemOut'];
export type Quest = Trpg['schemas']['QuestOut'];
export type TableMap = Trpg['schemas']['MapOut'];
export type GameClock = Trpg['schemas']['ClockOut'];
export type ClockTime = Trpg['schemas']['ClockTimeOut'];
export type SceneCast = Trpg['schemas']['SceneCastOut'];
export type ScenePerson = Trpg['schemas']['PersonOut'];
export type SceneMonster = Trpg['schemas']['SceneMonsterOut'];
export type DeclaredAction = NonNullable<Trpg['schemas']['DeclarationOut']['action']>;
export type TableEvent = Trpg['schemas']['EventOut'];
export type EventPage = Trpg['schemas']['EventPage'];
export type ChatMessage = Trpg['schemas']['MessageOut'];
export type MessagePage = Trpg['schemas']['MessagePage'];
export type WhisperPage = Trpg['schemas']['WhisperPage'];

export type PublicCharacterPage = Asset['schemas']['PublicCharacterPage'];
export type PublicCharacterSummary = Asset['schemas']['PublicCharacterSummary'];

export type ConversationPage = Chat['schemas']['ConversationPage'];
export type ConversationSummary = Chat['schemas']['ConversationSummary'];

// 결제 서버의 지갑(A6)과 충전(A7). 크레딧의 양은 글자다("80"). 화면이 셈하지 않는다. 상품과 주문의 값(price)은 원이고 숫자다
export type Wallet = Billing['schemas']['Wallet'];
export type WalletEntry = Billing['schemas']['Entry'];
export type WalletEntries = Billing['schemas']['Entries'];
export type Product = Billing['schemas']['Product'];
export type Order = Billing['schemas']['Order'];
// 주문 목록과 상품 목록은 이름 붙은 스키마가 없어 응답의 모양을 그대로 쓴다
export type OrderPage = BillingOperations['listOrders']['responses'][200]['content']['application/json'];

// 운영자의 신고 처리(E4, #678). 캐릭터의 신고는 asset, 대화 속 답의 신고는 chat 의 것이다.
// 사유와 처리의 값은 두 서버가 같다(spam, abuse, sexual, minor, illegal, other / actioned, dismissed)
export type ReportReason = Asset['schemas']['ReportReason'];
export type ReportOutcome = Asset['schemas']['ReportOutcome'];
export type OutcomeInput = Asset['schemas']['OutcomeInput'];
export type OutcomeResult = Asset['schemas']['OutcomeResult'];
export type HiddenInput = Asset['schemas']['HiddenInput'];
export type HiddenResult = Asset['schemas']['HiddenResult'];
export type CharacterReportPage = Asset['schemas']['OpenReportPage'];
export type CharacterReportGroup = Asset['schemas']['OpenReportGroupOut'];
export type CharacterReport = Asset['schemas']['ReportOut'];
export type MessageReportPage = Chat['schemas']['ReportPage'];
export type MessageReportSummary = Chat['schemas']['ReportSummaryOut'];
export type MessageReportDetail = Chat['schemas']['ReportDetailOut'];
export type ReportContextMessage = Chat['schemas']['ContextMessageOut'];
