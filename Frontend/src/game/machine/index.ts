/** game/machine —— 游戏主状态机 */
export { createGameMachine, getInitialStateValue } from './gameMachine'
export type { GameMachine } from './gameMachine'
export { useGameMachine, restoreMachineState, resetMachineState } from './useGameMachine'
export type { GameScreen, GameEvent } from './types'
export { isGameScreen } from './types'
