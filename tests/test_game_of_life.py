from game_of_life import evolve, grid_from_alive, render_grid


def test_block_still_life_stays_the_same() -> None:
    grid = grid_from_alive(rows=4, cols=4, alive={(1, 1), (1, 2), (2, 1), (2, 2)})
    assert evolve(grid) == grid


def test_blinker_oscillates_to_vertical_line() -> None:
    grid = grid_from_alive(rows=5, cols=5, alive={(2, 1), (2, 2), (2, 3)})
    next_grid = evolve(grid)
    assert next_grid == grid_from_alive(rows=5, cols=5, alive={(1, 2), (2, 2), (3, 2)})


def test_render_grid_uses_live_and_dead_symbols() -> None:
    grid = grid_from_alive(rows=2, cols=3, alive={(0, 1), (1, 2)})
    assert render_grid(grid) == ".O.\n..O"
