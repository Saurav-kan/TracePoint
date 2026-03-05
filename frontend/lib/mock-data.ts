export interface Case {
  id: string;
  title: string;
  brief: string;
  status: 'active' | 'closed' | 'archived';
  date: string;
  priority: 'high' | 'medium' | 'low';
}

export interface Evidence {
  id: string;
  type: 'witness' | 'gps' | 'cctv' | 'forensic';
  label: string;
  reliability: number;
  timestamp: string;
  summary: string;
}

export const MOCK_CASES: Case[] = [
  {
    id: 'case-001',
    title: 'Downtown Vault Breach',
    brief: 'Unauthorized access to the main vault at 02:00 AM. Contradictory witness reports regarding security patrol timing.',
    status: 'active',
    date: '2026-03-01',
    priority: 'high',
  },
  {
    id: 'case-002',
    title: 'Harbor Pier Multi-Vehicle Incident',
    brief: 'Chain reaction collision involving three commercial vessels and pier infrastructure.',
    status: 'active',
    date: '2026-03-02',
    priority: 'medium',
  },
  {
    id: 'case-003',
    title: 'Metro Cyber-Exfiltration',
    brief: 'Investigation into large-scale data transfer to offshore nodes during maintenance window.',
    status: 'closed',
    date: '2026-02-28',
    priority: 'high',
  },
];

export const MOCK_EVIDENCE: Evidence[] = [
  {
    id: 'ev-1',
    type: 'gps',
    label: 'Unit-77 GPS Log',
    reliability: 0.98,
    timestamp: '2026-03-01 02:15:00',
    summary: 'Subject vehicle located at [40.7128, -74.0060]. No deviation from path.',
  },
  {
    id: 'ev-2',
    type: 'witness',
    label: 'Witness Statement: Security Guard',
    reliability: 0.65,
    timestamp: '2026-03-01 02:10:00',
    summary: 'Reported seeing a dark sedan leaving the north exit.',
  },
  {
    id: 'ev-3',
    type: 'cctv',
    label: 'North Gate CCTV Feed',
    reliability: 0.92,
    timestamp: '2026-03-01 02:12:00',
    summary: 'Vague silhouette detected. Match probability: 45%.',
  },
];
