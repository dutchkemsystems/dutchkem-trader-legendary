"""
Feature 8: Genetic Algorithm Parameter Optimization
Uses GA to optimize strategy parameters based on recent performance.
"""
import numpy as np
import random
from typing import Dict, List, Callable, Tuple
from dataclasses import dataclass
import json
from pathlib import Path
import logging

log = logging.getLogger("ga_optimizer")


@dataclass
class Individual:
    genes: Dict[str, float]
    fitness: float = 0.0


class GeneticOptimizer:
    """Optimize strategy parameters using genetic algorithm."""

    def __init__(self, param_ranges: Dict[str, Tuple[float, float]] = None):
        self.param_ranges = param_ranges or {
            "sl_atr_mult": (1.0, 3.0),
            "tp_atr_mult": (2.0, 6.0),
            "rsi_period": (7, 21),
            "bb_period": (14, 30),
            "score_threshold": (2.0, 4.0),
            "trailing_breakeven_rr": (0.5, 1.5),
            "trailing_step_rr": (1.5, 3.0),
        }
        self.population_size = 20
        self.generations = 10
        self.mutation_rate = 0.1
        self.crossover_rate = 0.7
        self.population = []
        self.best_individual = None
        self.history = []

    def create_individual(self) -> Individual:
        """Create a random individual."""
        genes = {}
        for param, (min_val, max_val) in self.param_ranges.items():
            genes[param] = random.uniform(min_val, max_val)
        return Individual(genes=genes)

    def initialize_population(self):
        """Create initial population."""
        self.population = [self.create_individual() for _ in range(self.population_size)]

    def evaluate(self, individual: Individual, backtest_fn: Callable) -> float:
        """Evaluate individual using backtest function."""
        try:
            fitness = backtest_fn(individual.genes)
            individual.fitness = fitness
            return fitness
        except Exception as e:
            individual.fitness = -999
            return -999

    def select(self) -> Individual:
        """Tournament selection."""
        tournament = random.sample(self.population, min(3, len(self.population)))
        return max(tournament, key=lambda ind: ind.fitness)

    def crossover(self, parent1: Individual, parent2: Individual) -> Individual:
        """Uniform crossover."""
        child_genes = {}
        for param in self.param_ranges:
            if random.random() < 0.5:
                child_genes[param] = parent1.genes[param]
            else:
                child_genes[param] = parent2.genes[param]
        return Individual(genes=child_genes)

    def mutate(self, individual: Individual):
        """Random mutation."""
        for param, (min_val, max_val) in self.param_ranges.items():
            if random.random() < self.mutation_rate:
                # Gaussian mutation
                current = individual.genes[param]
                mutation = random.gauss(0, (max_val - min_val) * 0.1)
                individual.genes[param] = max(min_val, min(max_val, current + mutation))

    def evolve(self, backtest_fn: Callable) -> Dict:
        """Run genetic algorithm optimization."""
        self.initialize_population()

        for gen in range(self.generations):
            # Evaluate population
            for individual in self.population:
                self.evaluate(individual, backtest_fn)

            # Sort by fitness
            self.population.sort(key=lambda ind: ind.fitness, reverse=True)

            # Track best
            if self.population[0].fitness > (self.best_individual.fitness if self.best_individual else -999):
                self.best_individual = Individual(
                    genes=self.population[0].genes.copy(),
                    fitness=self.population[0].fitness,
                )

            self.history.append({
                "generation": gen,
                "best_fitness": self.population[0].fitness,
                "avg_fitness": np.mean([ind.fitness for ind in self.population]),
            })

            log.info(f"GA Gen {gen}: best={self.population[0].fitness:.4f}, "
                     f"avg={np.mean([ind.fitness for ind in self.population]):.4f}")

            # Create new population
            new_population = [self.population[0]]  # Elitism

            while len(new_population) < self.population_size:
                parent1 = self.select()
                parent2 = self.select()

                if random.random() < self.crossover_rate:
                    child = self.crossover(parent1, parent2)
                else:
                    child = Individual(genes=parent1.genes.copy())

                self.mutate(child)
                new_population.append(child)

            self.population = new_population

        return {
            "best_params": self.best_individual.genes,
            "best_fitness": self.best_individual.fitness,
            "generations": self.generations,
            "history": self.history,
        }

    def save_results(self, filepath: str):
        """Save optimization results."""
        data = {
            "best_params": self.best_individual.genes if self.best_individual else {},
            "best_fitness": self.best_individual.fitness if self.best_individual else 0,
            "history": self.history,
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def load_results(self, filepath: str) -> bool:
        """Load optimization results."""
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                self.best_individual = Individual(
                    genes=data.get("best_params", {}),
                    fitness=data.get("best_fitness", 0),
                )
                self.history = data.get("history", [])
                return True
        except Exception as e:
            log.warning(f"Failed to load GA results: {e}")
            return False
