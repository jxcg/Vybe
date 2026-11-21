import {
  Beer,
  Check,
  Clock,
  Coffee,
  Dices,
  Film,
  Footprints,
  Heart,
  Laugh,
  MapPin,
  MicVocal,
  Moon,
  Music,
  Palette,
  Sparkles,
  Star,
  Ticket,
  Trophy,
  Users,
  Utensils,
  Wallet,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { RainMark } from './RainMark';

// The reason icons the server may name (listed in web/INTEGRATION.md). Unknown names get a check.
const ICONS: Record<string, LucideIcon> = {
  Beer,
  Clock,
  Coffee,
  Dices,
  Film,
  Footprints,
  Heart,
  Laugh,
  MapPin,
  MicVocal,
  Moon,
  Music,
  Palette,
  Sparkles,
  Star,
  Ticket,
  Trophy,
  Users,
  Utensils,
  Wallet,
  Zap,
};

export function ReasonIcon({ name }: { name: string }) {
  // Rain uses the app's own rain mark rather than the stock cloud.
  if (name === 'CloudRain') return <RainMark />;
  const Icon = ICONS[name] ?? Check;
  return <Icon size={18} strokeWidth={2} aria-hidden="true" />;
}
