import scipy
import scipy.special as Sp
import numpy as np
import xmod
import time
import logging
import tempfile

class freyr:
    def __init__(self,data,K=100):
        self.data=data
        self.V=self.data[2].max()+1
        """We augment the feature indices in data[3] by one, reserving 0 for the absence of a feature"""
        self.F=self.data[3].max()+1-1
        self.J=self.data[0].max()+1
        self.nj=doccounts(data[1])
        self.Nj=int(self.nj.sum())
        self.K=K

        self.theta=np.ones(self.K)/self.K
        self.beta=np.ones(self.V)/self.V
        self.gamma=np.ones(self.F)/self.F

        self.phi=np.clip(dirichletrnd(self.beta,self.K),1e-10,1-1e-10);
        self.psi=np.clip(dirichletrnd(self.gamma,self.K),1e-10,1-1e-10);
        self.pi=np.clip(dirichletrnd(self.theta,self.J),1e-10,1-1e-10);

        self.phiprior=dirichlet()
        self.psiprior=dirichlet()
        self.piprior=dirichlet()

        self.init_iteration_max=1e+2
        self.mcmc_iteration_max=1e+3
        self.iteration_eps=1e-5
        self.verbose=0

    def mcmc(self):
        iteration=0
        self.ll=np.empty(self.mcmc_iteration_max,float)

        while iteration<self.mcmc_iteration_max:
            self.fast_posterior()
            self.gamma_a_mle()
            self.theta_a_mle()
            self.beta_a_mle()

            self.ll[iteration]=self.pseudologlikelihood

            if self.verbose:
                logging.warning("LL[%4d] = %f" % (iteration, self.pseudologlikelihood))
            iteration+=1



    def fast_posterior(self):
        vpsi=np.hstack(( np.ones((self.K,1)),self.psi))
        self.Rphi,self.Rpsi,self.S,Z=xmod.xfactorialposterior(self.phi,vpsi,self.pi,self.data,self.Nj,self.V,self.F+1,self.J,self.K)

        phi=np.clip(dirichletrnd_array(self.Rphi+self.beta),1e-10,1-1e-10);
        psi=np.clip(dirichletrnd_array(self.Rpsi[:,1:]+self.gamma),1e-10,1-1e-10);
        vpi=np.clip(dirichletrnd_array(self.S+self.theta),1e-10,1-1e-10)

        self.phi=np.ascontiguousarray((phi.T/phi.sum(1)).T)
        self.psi=np.ascontiguousarray((psi.T/psi.sum(1)).T)
        self.pi=np.ascontiguousarray((vpi.T/vpi.sum(1)).T)

        self.pseudologlikelihood=Z

    def beta_a_mle(self):
        self.phiprior.observation(self.phi)
        self.phiprior.a=self.beta.sum()
        self.phiprior.m=np.ones(self.V)/self.V
        self.phiprior.a_update()
        self.beta=self.phiprior.a*self.phiprior.m

    def theta_a_mle(self):
        self.piprior.observation(self.pi)
        self.piprior.a=self.theta.sum()
        self.piprior.m=np.ones(self.K)/self.K
        self.piprior.a_update()
        self.theta=self.piprior.a*self.piprior.m

    def gamma_a_mle(self):
        self.psiprior.observation(self.psi)
        self.psiprior.a=self.gamma.sum()
        self.psiprior.m=np.ones(self.F)/self.F
        self.psiprior.a_update()
        self.gamma=self.psiprior.a*self.psiprior.m

    def getlatentlabels(self,k=10):
        self.latent_labels=[]
        for j in np.arange(self.K):
            Lphi=[]
            Lpsi=[]
            for i in np.flipud(np.argsort(self.phi[j])[-k:]):
                Lphi.append((self.vocab_labels[i],self.phi[j,i])),
            for i in np.flipud(np.argsort(self.psi[j])[-k:]):
                continue
                Lpsi.append((self.feature_labels[i],self.psi[j,i])),
            self.latent_labels.append((Lphi,Lpsi))

    def printlatentlabels(self,k=10):
        self.getlatentlabels(k)
        k=0
        for l in self.latent_labels:
            k+=1
            print str(k)+': ',
            for i in l[0]:
                print '%s(%2.4f)' % (i[0],i[1]),
            print "\n",
            for j in l[1]:
                print '%s(%2.4f)' % (j[0],j[1]),
            print "\n\n",

    def getfeaturelabels(self,file):
        self.feature_labels=open(file).read().split()

    def getvocablabels(self,file):
        self.vocab_labels=open(file).read().split()

class dirichlet:
    def __init__(self,K=10):
        self.K=K
        self.iteration_eps=1e-5
        self.iteration_max=10
        self.mcmc_stepsize=1e-1
        self.mcmc_iteration_max=25

    def observation(self,data):
        self.data=np.clip(data,1e-10,1-1e-10)
        self.J=data.shape[0]
        self.K=data.shape[1]
        self.logdatamean=np.log(self.data).mean(axis=0)

    def initialize(self):
        self.a,self.m=moment_match(self.data)

    def loglikelihood_gradient(self):
        return self.J*(psi(self.a)-psi(self.a*self.m)  + self.logdatamean)

    def loglikelihood(self):
        return self.J*(Sp.gammaln(self.a)-Sp.gammaln(self.a*self.m).sum()+np.dot(self.a*self.m-1,self.logdatamean))

    def a_new(self):
        d1=self.J*(psi(self.a) - np.dot(self.m,psi(self.a*self.m)) + np.dot(self.m,self.logdatamean));
        d2=self.J*(psi(self.a,1) - np.dot(self.m**2,psi(self.a*self.m,1)));
        self.a= (1/self.a+d1/d2/self.a**2)**-1

    def m_new(self):
        digamma_am= self.logdatamean-np.dot(self.m,self.logdatamean-psi(self.a*self.m))
        am=inv_digamma(digamma_am)
        self.m=am/np.sum(am)


    def a_update(self):
        a_old=self.a
        self.a_new()

        iteration=0

        while (abs(a_old-self.a)>self.iteration_eps) and iteration<self.iteration_max:
            a_old=self.a
            self.a_new()
            iteration+=1

    def m_update(self):
        m_old=self.m
        self.m_new()

        iteration=0

        while (abs(m_old-self.m).max()>self.iteration_eps) and iteration<self.iteration_max:
            m_old=self.m
            self.m_new()
            iteration+=1


    def mle(self):
        am_old=self.a*self.m
        self.a_update()
        self.m_update()

        iteration=0
        #print self.loglikelihood()

        while (abs(am_old-self.m*self.a).max()>self.iteration_eps) and iteration<self.iteration_max:
            am_old=self.a*self.m
            self.a_update()
            self.m_update()
            iteration+=1
            #print self.loglikelihood()

    def mcmc(self,mcmc_iteration_max=100):

        theta_current=self.a*self.m
        ll_current=self.loglikelihood()
        self.ll=zeros(mcmc_iteration_max)
        self.switch=zeros(mcmc_iteration_max)
        self.Theta=zeros((mcmc_iteration_max,self.K))

        iteration=0

        while iteration<mcmc_iteration_max:
            theta_proposed=theta_current*(1+np.random.uniform(-self.mcmc_stepsize,self.mcmc_stepsize,self.K))

            self.a=theta_proposed.sum()
            self.m=theta_proposed/self.a
            ll_proposed=self.loglikelihood()

            if exp(ll_proposed-ll_current)>np.random.rand():
                ll_current=ll_proposed
                self.switch[iteration]=1
                theta_current=theta_proposed

            self.ll[iteration]=ll_current
            self.Theta[iteration]=theta_current

            iteration+=1


def doccounts(wordnumcol):
    counts = []
    lastwordnum = -1
    count = 0
    for wordnum in wordnumcol:
        if wordnum < lastwordnum:
            counts.append(count)
            count = 0
        count += 1
        lastwordnum = wordnum
    counts.append(count)
    return np.array(counts, float)


def norm(x):
    return sqrt(np.sum(x**2))


def vdiff(n,p):
    return norm(n - p) / norm(n)


def slice_array_by_cols(p,ind):
    return np.ascontiguousarray(p[:,ind])


def logsumexp(A,axis_n=1):
    """ logsumexp - summing along rows """
    if A.ndim==1:
        M=A.max()
        return M+np.log(exp((A.T-M).T).sum())
    elif axis_n==1:
        M=A.max(axis=1)
        return M+np.log(exp((A.T-M).T).sum(axis=1))
    else:
        M=A.max(axis=0)
        return M+np.log(exp(A-M).sum(axis=0))


def logharmonic(ll):
    return np.log(len(ll))-logsumexp(-ll)

# some random number generators
def dirichletrnd(a,J):
    g=np.random.gamma(a,size=(J,np.shape(a)[0]))
    return (g.T/np.sum(g,1)).T

def multinomialrnd(p,n):
    return argmax(np.random.uniform(0,1,(n,1))  <tile(cumsum(p),(n,1)),axis=1)


def multinomialrnd_array(p,N=1):
    """ Each row of p is a probability distribution. Draw single sample from each."""
    return argmax(np.random.uniform(0,1,(np.shape(p)[0],1))  <cumsum(p,1),1)


def dirichletrnd_array(a):
    g=np.random.gamma(a)
    return (g.T/np.sum(g,1)).T

def betarnd_array(a,b):
        a_sample=np.random.gamma(a)
        b_sample=np.random.gamma(b)
        return a_sample/(a_sample+b_sample)

def itersplit(s, sub):
    pos = 0
    while True:
        i = s.find(sub, pos)
        if i == -1:
            yield s[pos:]
            break
        else:
            yield s[pos:i]
            pos = i + len(sub)

def int2bytes(i8):
    s = ""
    for bi in xrange(8):
        b = i8 & 0xFF
        s += chr(b)
        i8 >>= 8
    return s

def parse_item(item):
    item = item.strip()
    if "," in item:
        left, tworight = item.split(",")
        retval = [left] + tworight.split(":")
    else:
        retval = item.split(":")
    return map(int, retval)

def dataread(file):
    #return np.load(file).T

    tmpfile = open("binary.dat", "wb")

    #tmpfile = tempfile.NamedTemporaryFile(delete=False)
    #print tmpfile.name

    tmpfile.write("\x93\x4e\x55\x4d\x50\x59\x01\x00\x46\x00")

    data_file=open(file)
    dimensions = 2
    total_count = 0
    logging.warning("Starting to read data (pass 1)...")
    for doc_id, doc in enumerate(data_file):
        for item in itersplit(doc, " "):
            splitted = parse_item(item)
            total_count += splitted[-1]
            if len(splitted) == 2:
                pass
            elif len(splitted) == 3:
                dimensions = 2
            else:
                raise ValueError("Doc %d is invalid (item %d: '%s')" % (group_j, item_i, item))

    data_file.close()

    # okay let's go through this again
    # start writing the header.
    header = "{'descr': '<i8', 'fortran_order': False, 'shape': (%d, %d), }" % (total_count, dimensions + 2)
    header = ("%-69s\x0a" % header)
    tmpfile.write(header)

    # so far recognizes two data-types, lda and combinatorial lda
    data_file=open(file)
    group_j=0

    dimensions = 1
    logging.warning("Starting to read data (pass 2)...")
    for doc_id, doc in enumerate(data_file):
        this_doc = []
        doc_counter = 0
        for item in itersplit(doc, " "):
            splitted = parse_item(item)
            if len(splitted) == 2:
                feat_id = 0
                word_id, count = splitted
            elif len(splitted) == 3:
                word_id, feat_id, count = splitted

            for x in xrange(count):
                if False and dimensions == 1:
                    a = [doc_id, doc_counter, word_id]
                else:
                    a = [doc_id, doc_counter, word_id, feat_id]
                tmpfile.write("".join(map(int2bytes, a)))
                doc_counter += 1

    tmpfile.close()
    data = np.load(tmpfile.name)
    del tmpfile

    return data.T

def moment_match(data):
    """ Approximate the mean (m)  and precision (a)  of dirichlet distribution
    by moment matching.
    m is mean(data,0)
    a is given by Ronning (1989) formula
    """
    m=data.mean(axis=0)
    s=np.log(m*(1-m)/var(data,0)-1).sum()
    return exp(s/(data.shape[1]-1)),m

def psi(x,d=0):
    if type(x)==np.ndarray:
        s=x.shape
        x=x.flatten()
        n=len(x)

        y=np.empty(n,float)
        for i in xrange(n):
            y[i]=Sp.polygamma(d,x[i])

        return y.reshape(s)
    #elif type(x)==int or type(x)==float:
    else:
        return Sp.polygamma(d,x)



def inv_digamma(y,niter=5):
    x = exp(y)+1/2.0;
    Ind=(y<=-2.22).nonzero()
    x[Ind] = -1/(y[Ind] - psi(1));

    for iter in xrange(niter):
          x = x - (psi(x)-y)/psi(x,1);

    return x





