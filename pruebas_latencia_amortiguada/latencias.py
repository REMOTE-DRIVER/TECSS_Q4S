import random
import matplotlib.pyplot as plt
from datetime import datetime
import argparse

def save_latencies_to_file(latencies):
    """
    Saves a list of latencies to a file. The filename is based on the current timestamp.

    Parameters:
        latencies (list): List of latency values.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")[:-3]  # Up to milliseconds
    filename = f"latencies_{timestamp}.txt"
    with open(filename, 'w') as file:
        file.write("\n".join(map(str, latencies)))
    print(f"Latencies saved to {filename}")

def load_latencies_from_file(filename):
    """
    Loads a list of latencies from a file.

    Parameters:
        filename (str): Name of the file to load the latencies from.

    Returns:
        list: A list of latencies loaded from the file.
    """
    with open(filename, 'r') as file:
        return [int(line.strip()) for line in file]

def generate_realistic_latencies(size=1000, max_latency=360, stable_period=100):
    """
    Generates a list of realistic latencies with trends, sudden spikes, and stability.

    Parameters:
        size (int): Number of latencies to generate.
        max_latency (int): Maximum possible latency value.
        stable_period (int): Average number of packets for stable trends.

    Returns:
        list: A list of latencies simulating realistic network behavior.
    """
    latencies = []
    current_latency = random.randint(0, max_latency // 10)

    for i in range(size):
        if random.random() < 0.1:  # 1% chance of a sudden spike
            latencies.append(random.randint(max_latency * 3 // 4, max_latency))
        elif random.random() < 0.1:  # 5% chance of a random jump
            current_latency = random.randint(0, max_latency)
        elif len(latencies) % stable_period == 0:  # Change trend every stable_period
            trend = random.choice(["up", "down", "stable"])
            if trend == "up":
                current_latency = min(max_latency, current_latency + random.randint(5, 15))
            elif trend == "down":
                current_latency = max(0, current_latency - random.randint(5, 15))

        # Add some randomness within a small range to simulate jitter
        jitter = random.randint(-3, 3)
        latencies.append(max(0, min(max_latency, current_latency + jitter)))

    return latencies

def generate_realistic_latencies_2(size=1000, max_latency=360, stable_period=100):
    """
    Generates a list of realistic latencies with trends, sudden spikes, and stability.

    Parameters:
        size (int): Number of latencies to generate.
        max_latency (int): Maximum possible latency value.
        stable_period (int): Average number of packets for stable trends.

    Returns:
        list: A list of latencies simulating realistic network behavior.
    """
    latencies = []
    current_latency = random.randint(0, max_latency // 10)
    trend_direction = 0  # 0 for stable, 1 for up, -1 for down
    
    for i in range(size):
        if random.random() < 0.01:  # 1% chance of a sudden spike
            latencies.append(random.randint(max_latency * 3 // 4, max_latency))
        elif random.random() < 0.00:  # 5% chance of a random jump
            current_latency = random.randint(0, max_latency)
        elif len(latencies) % stable_period == 0:  # Change trend every stable_period
            trend_direction = random.choice([1, -1, 0])  # Up, down, or stable

        # Apply trend more linearly
        if trend_direction == 1:  # Increasing trend
            current_latency = min(max_latency, current_latency + random.randint(1, 5))
        elif trend_direction == -1:  # Decreasing trend
            current_latency = max(0, current_latency - random.randint(1, 5))

        # Add some randomness within a small range to simulate jitter
        jitter = random.randint(-2, 2)
        latencies.append(max(0, min(max_latency, current_latency + jitter)))

    return latencies



def amortiguate_latency_slow(real_latencies):
    """
    Smooths out the latency values by limiting the change rate.

    Parameters:
        real_latencies (list): List of original latency values.

    Returns:
        list: List of amortiguated latency values.
    """
    topes = [3,5,7,9]# definen crecimiento y diferencia de latencia, jj recomienda de 3,4,5,6
    indice_subida = 0
    indice_bajada = 0
    amortiguated_latencies = []
    last_latency = real_latencies[0]  # Start with the first value
    for new_latency in real_latencies:
        if new_latency > last_latency + topes[indice_subida]:
            smoothed_latency = last_latency + topes[indice_subida]
            if indice_subida == len(topes)-1:
                pass
            else:
                indice_subida +=1
            indice_bajada = 0
        elif new_latency < last_latency - topes[indice_bajada]:
            smoothed_latency = last_latency - topes[indice_bajada]
            if indice_bajada == len(topes)-1:
                pass
            else:
                indice_bajada +=1
            indice_subida = 0
        else:
            indice_subida = 0
            indice_bajada = 0
            smoothed_latency = new_latency
        #Si la diferencia no es mayor que el tope se estabiliza
        #para bajar igual, si es menor que el tope, se baja, indice_bajada
        #
        '''if new_latency > last_latency + 1:
            smoothed_latency = last_latency + 1
        elif new_latency < last_latency - 1:
            smoothed_latency = last_latency - 1
        else:
            smoothed_latency = new_latency'''
        amortiguated_latencies.append(smoothed_latency)
        last_latency = smoothed_latency  # Update for the next iteration
    return amortiguated_latencies

def exp(real_latencies,alpha):
    #alpha = 0.01 #Factor de suavizado, cuanto mas cerca de 1 detecta cambios mas rapidamente
    amortiguated_latencies = []
    last_latency = real_latencies[0]  # Start with the first value
    for new_latency in real_latencies:
        smoothed_latency = alpha * new_latency + (1 - alpha) * last_latency
        last_latency = smoothed_latency
        amortiguated_latencies.append(smoothed_latency)
    return amortiguated_latencies

def simple(real_latencies,n):
    #n es el numero de paquetes para encontrar la latencia real, si es 100 igual que el exponencial
    amortiguated_latencies = []
    last_latency = real_latencies[0]  # Start with the first value
    for new_latency in real_latencies:
        delta = new_latency - last_latency
        smoothed_latency = last_latency + delta / n
        last_latency = smoothed_latency
        amortiguated_latencies.append(smoothed_latency)
    return amortiguated_latencies


def plot_latencies(latencies_list, title="Latency Over Time"):
    """
    Plots latencies over time.

    Parameters:
        latencies_list (list): List of latency lists to plot.
        title (str): Title of the plot.
    """
    plt.figure(figsize=(12, 6))
    plt.plot(latencies_list[0], label="Original Latencies", color="blue")
    #plt.plot(latencies_list[3], label="Fast", color="green")
    #plt.plot(latencies_list[2], label="Steps", color="green")
    #plt.plot(latencies_list[1], label="Linear", color="orange")
    plt.xlabel("Time (index)")
    plt.ylabel("Latency (ms)")
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.show()

# Example usage:
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Latency Simulation Tool")
    parser.add_argument("-l", "--load", type=str, help="Load latencies from a file")
    args = parser.parse_args()

    if args.load:
        print(f"Loading latencies from file: {args.load}")
        latencies = load_latencies_from_file(args.load)
    else:
        print("Generating new latencies...")
        latencies = generate_realistic_latencies_2(size=1000)
        save_latencies_to_file(latencies)

    amortiguated_latencies = amortiguate_latency_slow(latencies)
    #exp_latency = amortiguated_latencies_exp(latencies)
    simple_latency_slow = simple(latencies,360)
    simple_latency_medium = simple(latencies,100)
    simple_latency_fast = simple(latencies,20)
    #exp_latency = amortiguated_latencies_exp(latencies)
    exp_latency_slow = exp(latencies,0.00002)#0.002) #naranja
    exp_latency_medium = exp(latencies,0.4)#0.01) #verde
    #exp_latency_fast = exp(latencies,0.36)#0.036)

    #plot_latencies([latencies,simple_latency_fast,amortiguated_latencies],title="Linear latency VS Steps")
    #plot_latencies([latencies, exp_latency_slow,exp_latency_medium],title="Latency Over Time Exponential Smoothing")
    plot_latencies([latencies],title="Latency Over Time Exponential Smoothing")

    print(simple(range(100),10))


