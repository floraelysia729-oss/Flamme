import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { GraphNeighborsPanel } from './GraphNeighborsPanel'

const getNeighborsMock = vi.fn()

vi.mock('../../lib/flamme/client', () => ({
  createFlammeClient: () => ({
    getNeighbors: getNeighborsMock,
  }),
}))

describe('GraphNeighborsPanel', () => {
  it('shows empty state when there are no neighbors', async () => {
    getNeighborsMock.mockResolvedValue({
      node: 'Test',
      neighbors: [],
      degree: 0,
    })

    render(
      <GraphNeighborsPanel
        nodeName="Test"
        vaultPath="/vault"
        enabled
        onNavigate={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText(/暂无邻居/)).toBeInTheDocument()
    })
  })

  it('renders neighbor list', async () => {
    getNeighborsMock.mockResolvedValue({
      node: 'Test',
      neighbors: [{ id: 'n1', label: 'Neighbor', relation: 'related_to' }],
      degree: 1,
    })

    render(
      <GraphNeighborsPanel
        nodeName="Test"
        vaultPath="/vault"
        enabled
        onNavigate={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Neighbor')).toBeInTheDocument()
    })
  })
})
