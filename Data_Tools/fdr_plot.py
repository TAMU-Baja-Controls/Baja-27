import matplotlib.pyplot as plt

fdr = [4.5, 5, 5.5, 6, 6.5, 7.26, 8]
gaged = [5.905, 5.86, 5.844, 5.847, 5.864, 5.918, 5.974]

plt.plot(fdr, gaged, 'o-', label="Predicted Accel Time (Gaged '26 on Asphalt)")
plt.plot(7.26, 5.927, 'ro', label='Recorded Time')
plt.xlabel('FDR')
plt.ylabel('Accel Time')
plt.legend()
plt.show()