import { StoreProvider, useStore } from './state/store';
import { Board } from './components/Board';
import { LoadingScreen } from './components/LoadingScreen';
import { ReconnectBanner } from './components/ReconnectBanner';
import { StartScreen } from './components/StartScreen';
import { TicketStack } from './components/TicketStack';
import { Toasts } from './components/Toasts';

function Screens() {
  const { state } = useStore();
  return (
    <div className="app">
      {state.screen === 'start' && <StartScreen />}
      {state.screen === 'loading' && <LoadingScreen />}
      {state.screen === 'board' && <Board />}
      {state.screen === 'board' && state.ticket && <TicketStack key={state.ticket.id} open={state.ticket} />}
      <ReconnectBanner />
      <Toasts />
    </div>
  );
}

export default function App() {
  return (
    <StoreProvider>
      <Screens />
    </StoreProvider>
  );
}
