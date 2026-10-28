"""Liste lessicali usate dal rilevatore di nomi di persona.

FIRST_NAMES: nomi propri (italiani + alcuni stranieri comuni). Un sequenza di
parole maiuscole viene considerata un nome di persona se contiene almeno uno di
questi nomi. Si possono aggiungere nomi dall'interfaccia (Impostazioni).

Sono stati esclusi di proposito i nomi che coincidono con parole comuni
(es. Pace, Gioia, Natale, Italia, Felice, Domenica) per ridurre i falsi positivi.
"""

_FIRST_NAMES_IT = """
Abele Ada Adalberto Adamo Addolorata Adele Adelaide Adelina Adolfo Adriana Adriano Agata Agnese
Agostino Aida Alba Alberta Alberto Alda Aldo Alessandra Alessandro Alessia Alessio Alfio Alfonsina
Alfonso Alfredo Alice Alida Alina Alma Amalia Amanda Ambra Ambrogio Amedeo Amelia Amilcare Anastasia
Andrea Angela Angelica Angelo Anita Anna Annalisa Annamaria Annarita Antonella Antonietta Antonino
Antonio Anselmo Arianna Armando Arnaldo Arturo Assunta Attilio Augusto Aurelio Aurora Barbara Bartolomeo
Beatrice Benedetta Benedetto Beniamino Bernardo Bettina Bianca Bruna Bruno Calogero Camilla Camillo
Carla Carlo Carlotta Carmela Carmelo Carmen Carmine Carolina Caterina Cecilia Cesare Chiara Cinzia
Cirillo Ciro Clara Claudia Claudio Clelia Clemente Concetta Corrado Cosimo Costantino Costanza Cristian
Cristiana Cristiano Cristina Cristoforo Damiano Daniela Daniele Dante Dario Davide Debora Delia Demetrio
Denis Denise Diana Diego Dino Domenico Donatella Donato Dora Edoardo Elda Elena Eleonora Elia Elio
Elisa Elisabetta Ellena Elvira Emanuela Emanuele Emilia Emiliano Emilio Emma Enrica
Enrico Enza Enzo Ercole Erica Ermanno Ernesto Ester Ettore Eugenia Eugenio Eva Evelina Fabiana Fabio
Fabrizia Fabrizio Federica Federico Fedele Ferdinando Fernanda Fernando Filippa Filippo Fiorella
Flavia Flavio Francesca Francesco Franco Gabriele Gabriella Gaetano Gaia Gemma Gennaro Gerardo
Giacomo Giada Giancarlo Gianfranco Gianluca Gianluigi Gianmarco Gianna Gianni Giannina Gianpaolo
Gianpiero Gilberto Gilda Gino Giordano Giorgia Giorgio Giosuè Giovanna Giovanni Giuditta Giulia
Giuliana Giuliano Giulio Giuseppa Giuseppe Giuseppina Glauco Gloria Graziella Gregorio Guglielmo
Guido Ida Ignazio Ilaria Ilenia Ines Irene Iris Isabella Italo Ivan Ivana Ivano Jacopo Jessica
Lamberto Lara Laura Lauro Lazzaro Lea Leandro Leonardo Letizia Lia Liana Licia Lidia Liliana Lina
Lino Livia Livio Lorella Lorena Lorenza Lorenzo Loredana Luana Luca Lucia Luciana Luciano Lucio
Ludovica Ludovico Luigi Luigia Luisa Maddalena Mafalda Manfredi Manuel Manuela Mara Marcella Marcello
Marco Margherita Maria Mariangela Marianna Mariano Marilena Marina Marino Mario Marisa Marta Martina
Martino Massimiliano Massimo Matilde Matteo Mattia Maurizio Mauro Melissa Michela Michele Milena
Mirella Miriam Mirko Monica Nadia Natalia Nazareno Nella Nicola Nicoletta Nicolò Niccolò Nicolo Nina
Nino Noemi Norberto Norma Oliviero Ombretta Orazio Oreste Orlando Ornella Oscar Ottavio Pamela
Paola Paolo Pasquale Patrizia Patrizio Pierluigi Piero Pietro Pio Piera Pierangelo Pierpaolo
Raffaele Raffaella Raimondo Rebecca Remo Renata Renato Riccardo Rina Rino Rita Roberta Roberto
Rocco Rodolfo Romano Romeo Romina Romolo Rosa Rosalba Rosalia Rosanna Rosaria Rosario Rossana
Rossella Ruggero Sabina Sabrina Salvatore Samuele Sandra Sandro Santina Sara Saverio Sebastiano
Selene Sergio Severino Silvana Silvano Silvia Silvio Simona Simone Sofia Sonia Stefania Stefano
Susanna Tamara Tania Tatiana Teodoro Teresa Tiziana Tiziano Tommaso Tullio Ugo Umberto Valentina
Valentino Valeria Valerio Vanessa Vania Vincenza Vincenzo Viola Virginia Vito Vittoria Vittorio
Viviana Walter Wanda Zaira
"""

_FIRST_NAMES_INTL = """
Adam Alan Albert Alex Alexander Amy Andrew Ann Anne Anthony Ben Benjamin Brian Catherine Charles
Charlotte Chris Christian Christopher Daniel David Elizabeth Emily Eric Frank George Henry Jack
Jacob James Jane Jennifer John Jonathan Joseph Julia Kate Kevin Laura Lisa Mark Mary Matthew Michael
Nicholas Oliver Patrick Paul Peter Richard Robert Ryan Sarah Simon Sophie Stephen Steven Thomas Tom
William Hans Jan Jens Klaus Lukas Pieter Sven Wolfgang Jean Pierre Philippe Marie Sophie Juan Jose
José Carlos Miguel Javier Pablo Ana Ahmed Mohamed Mohammed Ali Fatima Omar Yuki Hiroshi Wei Li
"""

FIRST_NAMES = {n.casefold() for n in (_FIRST_NAMES_IT + _FIRST_NAMES_INTL).split()}

# Titoli/appellativi: se precedono una sequenza maiuscola, questa è un nome
# anche senza nome proprio riconosciuto ("Sig. Rossi", "Mr Smith").
TITLE_WORDS = {
    w.casefold() for w in """
    Avv Avvocato Avvocatessa Dott Dottor Dottore Dottoressa Dr Prof Professor Professore
    Professoressa Ing Arch Geom Rag Sig Signor Signore Signora Signorina Signori Sigg Mr Mrs Ms
    Miss Mister Notaio Egr Gent Spett On Ill
    """.split()
}

# Parole maiuscole che non fanno mai parte di un nome di persona: spezzano la
# sequenza candidata.
STOPWORDS = {
    w.casefold() for w in """
    Il Lo La I Gli Le L Un Uno Una Di Del Dello Della Dei Degli Delle A Al Allo Alla Ai Agli Alle
    Da Dal Dallo Dalla Dai Dagli Dalle In Nel Nello Nella Nei Negli Nelle Con Su Sul Sullo Sulla
    Sui Sugli Sulle Per Tra Fra E Ed O Che Non Come Quando Dove Se Ma Anche Questo Questa Quello
    Quella Tutti Tutte Ogni Ciò Infatti Inoltre Pertanto Dunque Quindi Laddove Detta Detto Dette
    Lo Ecco Ai The Of And To For On At By From With Dear Hi Hello
    Giudice Pace Tribunale Corte Cassazione Cass Sezione Sezioni Unite Consiglio Procura Procuratore
    Codice Civile Penale Procedura Consumo Turismo Privacy Regolamento Direttiva Legge Decreto
    Costituzione Stato Repubblica Ministero Ministro Comune Provincia Regione Ufficio Agenzia Entrate
    Foro Giustizia Grazia Autorità Garante Ricorso Ricorrente Resistente Convenuta Convenuto Attore
    Attrice Contro Premessa Fatto Diritto Conclusioni Oggetto Parole Chiave Mezzi Prova Doc Docc
    All Allegato Allegati Euro Iva Pec Email Tel Fax Cell Via Viale Piazza Piazzale Corso Largo
    Vicolo Strada Contrada Località Borgo San Santa Santo Monte Porta Villa Ponte Torre Lago Isola
    Gennaio Febbraio Marzo Aprile Maggio Giugno Luglio Agosto Settembre Ottobre Novembre Dicembre
    Lunedì Martedì Mercoledì Giovedì Venerdì Sabato Domenica Ill.mo Spett.le Egr.
    Nord Sud Est Ovest Centro Italia Italiano Italiana Europa Europeo Europea Unione
    Srl Spa Snc Sas Gmbh Ltd Inc Llc Bv Nv Ag Sa Testimone Testimoni Teste Testi Parte Parti
    Avvocatura Studio Legale Notarile Società Banca Poste Italiane Spett Gentile Egregio Egregia
    Ricorrenti Resistenti Appellante Appellato Imputato Indagato Persona Offesa Querelante
    """.split()
}

# Città e paesi: non spezzano un nome (Messina, Napoli, Ferrara sono anche cognomi),
# ma non vengono mai propagati come cognome e vengono tolti ai bordi di un candidato.
CITIES = {
    w.casefold() for w in """
    Agrigento Alessandria Ancona Aosta Arezzo Ascoli Asti Avellino Bari Barletta Belluno Benevento
    Bergamo Biella Bologna Bolzano Brescia Brindisi Cagliari Caltanissetta Campobasso Caserta Catania
    Catanzaro Chieti Como Cosenza Cremona Crotone Cuneo Enna Fermo Ferrara Firenze Foggia Forlì
    Frosinone Genova Gorizia Grosseto Imperia Isernia Aquila Spezia Latina Lecce Lecco Livorno Lodi
    Lucca Macerata Mantova Massa Carrara Matera Messina Milano Modena Monza Brianza Napoli Novara Nuoro
    Oristano Padova Palermo Parma Pavia Perugia Pesaro Urbino Pescara Piacenza Pisa Pistoia Pordenone
    Potenza Prato Ragusa Ravenna Reggio Calabria Emilia Rieti Rimini Roma Rovigo Salerno Sassari Savona
    Siena Siracusa Sondrio Taranto Teramo Terni Torino Trapani Trento Treviso Trieste Udine Varese
    Venezia Verbania Vercelli Verona Vibo Valentia Vicenza Viterbo Italia Francia Germania Spagna
    Svizzera Austria Olanda Paesi Bassi Belgio Inghilterra Regno Unito Stati Uniti America Giappone
    Cina Corea Russia Grecia Portogallo Londra Parigi Berlino Madrid Amsterdam Bruxelles Vienna
    Zurigo Ginevra Monaco Francoforte Frankfurt Tokyo Seoul Pechino Netherlands
    """.split()
}

# Particelle ammesse all'interno di un nome (solo con iniziale maiuscola).
PARTICLES = {"de", "di", "da", "del", "della", "dello", "dei", "degli", "dal", "dalla",
             "la", "lo", "van", "von", "der", "den", "mc", "mac", "d'", "d’"}
