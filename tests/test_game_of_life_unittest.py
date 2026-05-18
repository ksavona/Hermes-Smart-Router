import unittest

from game_of_life import evolve, grid_from_alive, render_grid


class GameOfLifeTests(unittest.TestCase):
    def test_block_still_life_stays_the_same(self) -> None:
        grid = grid_from_alive(rows=4, cols=4, alive={(1, 1), (1, 2), (2, 1), (2, 2)})
        self.assertEqual(evolve(grid), grid)

    def test_blinker_oscillates_to_vertical_line(self) -> None:
        grid = grid_from_alive(rows=5, cols=5, alive={(2, 1), (2, 2), (2, 3)})
        next_grid = evolve(grid)
        expected = grid_from_alive(rows=5, cols=5, alive={(1, 2), (2, 2), (3, 2)})
        self.assertEqual(next_grid, expected)

    def test_render_grid_uses_live_and_dead_symbols(self) -> None:
        grid = grid_from_alive(rows=2, cols=3, alive={(0, 1), (1, 2)})
        self.assertEqual(render_grid(grid), ".O.\n..O")


if __name__ == "__main__":
    unittest.main()
